import hashlib
import logging
from pathlib import Path, PurePath
from collections import deque
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Deque, Type, TYPE_CHECKING

from dateutil.parser import parse
from git.objects.commit import Commit

from .cli.common import Game
from .metadata import Ckan
from .queue_handler import BaseMessageHandler, QueueHandler
from .repos import CkanMetaRepo
from .status import ModStatus
from .github_pr import GitHubPR


if TYPE_CHECKING:
    from mypy_boto3_sqs.service_resource import Message
    from mypy_boto3_sqs.type_defs import DeleteMessageBatchRequestEntryTypeDef
else:
    Message = object
    DeleteMessageBatchRequestEntryTypeDef = object

USER_AGENT = 'Mozilla/5.0 (compatible; Netkanbot/1.0; CKAN; +https://github.com/KSP-CKAN/NetKAN-Infra)'


class CkanMessage:

    def __init__(self, msg: Message,
                 ckm_repo: CkanMetaRepo, github_pr: Optional[GitHubPR] = None) -> None:
        self.body = msg.body
        self.ckan = Ckan(contents=self.body)
        # pylint: disable=invalid-name
        self.ModIdentifier: str
        self.GameId: str
        self.CheckTime: str
        self.FileName: str
        self.Success: bool
        self.Staged: bool
        self.ErrorMessage = None
        self.WarningMessages: Optional[str] = None
        # pylint: enable=invalid-name
        self.indexed = False
        for item in msg.message_attributes.items():
            attr_type = f'{item[1]["DataType"]}Value'
            content = item[1][attr_type]  # type: ignore[literal-required]
            if content.lower() in ['true', 'false']:
                content = content.lower() == 'true'
            if item[0] == 'FileName':
                content = PurePath(content).name
            setattr(self, item[0], content)
        self.md5_of_body = msg.md5_of_body
        self.message_id = msg.message_id
        self.receipt_handle = msg.receipt_handle
        self.ckm_repo = ckm_repo
        self.github_pr = github_pr

    def __str__(self) -> str:
        return f'{self.ModIdentifier}: {self.CheckTime}'

    @property
    def mod_path(self) -> Path:
        return self.ckm_repo.mod_path(self.ModIdentifier)

    @property
    def mod_file(self) -> Path:
        return self.mod_path.joinpath(self.FileName)

    @property
    def mod_version(self) -> str:
        return self.mod_file.stem

    @property
    def staging_branch_name(self) -> str:
        return f'add/{self.mod_version}'

    def mod_file_md5(self) -> str:
        with open(self.mod_file, mode='rb') as file:
            return hashlib.md5(file.read()).hexdigest()

    def metadata_changed(self) -> bool:
        if not self.mod_file.exists():
            return True
        if self.mod_file_md5() == self.md5_of_body:
            return False
        return True

    def write_metadata(self) -> None:
        self.mod_path.mkdir(exist_ok=True)
        with open(self.mod_file, mode='w', encoding='UTF-8') as file:
            file.write(self.body)

    def commit_metadata(self, file_created: bool) -> Commit:
        verb = 'added' if file_created else 'updated'
        commit = self.ckm_repo.commit(
            [self.mod_file.as_posix()],
            f'NetKAN {verb} mod - {self.mod_version}'
        )
        logging.info('Committing %s', self.mod_version)
        self.indexed = True
        return commit

    def status_attrs(self, new: bool = False) -> Dict[str, Any]:
        attrs: Dict[str, Any] = {
            'success': self.Success,
            'last_error': self.ErrorMessage,
            'last_warnings': self.WarningMessages,
            'last_inflated': parse(self.CheckTime),
            # If we're inflating it, it's not frozen
            'frozen': False,
        }
        resources = getattr(self.ckan, 'resources', None)
        if resources:
            attrs['resources'] = resources
        if new:
            attrs.update({
                'ModIdentifier': self.ModIdentifier,
                'game_id': self.GameId.lower(),
            })
        cache_path = self.ckan.cache_find_file
        if cache_path:
            cache_mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            attrs['last_downloaded'] = cache_mtime.astimezone(timezone.utc)
        if self.indexed:
            attrs['last_indexed'] = datetime.now(timezone.utc)
        release_date = getattr(self.ckan, 'release_date', None)
        if release_date:
            attrs['release_date'] = release_date
        return attrs

    def _process_ckan(self) -> None:
        if self.Success and self.metadata_changed():
            new_file = not self.mod_file.exists()
            self.write_metadata()
            self.commit_metadata(new_file)
        try:
            status = ModStatus.get(
                self.ModIdentifier, range_key=self.GameId.lower())
            attrs = self.status_attrs()
            if not self.Success and getattr(status, 'last_error', None) != self.ErrorMessage:
                logging.error('New inflation error for %s: %s',
                              self.ModIdentifier, self.ErrorMessage)
            elif (getattr(status, 'last_warnings', None) != self.WarningMessages and self.WarningMessages is not None):
                logging.error('New inflation warnings for %s: %s',
                              self.ModIdentifier, self.WarningMessages)
            actions = [getattr(ModStatus, key).set(val)
                       for key, val in attrs.items()]
            status.update(actions=actions)
        except ModStatus.DoesNotExist:
            ModStatus(**self.status_attrs(True)).save()

    def process_ckan(self) -> None:
        # Staged CKANs that were inflated successfully and have been changed
        if self.Staged and self.Success and self.metadata_changed():
            with self.ckm_repo.change_branch(self.staging_branch_name):
                self._process_ckan()
            if self.indexed and self.github_pr:
                self.github_pr.create_pull_request(
                    title=f'NetKAN inflated: {self.ModIdentifier}',
                    branch=self.staging_branch_name,
                    body=getattr(self, 'StagingReason',
                                 f'{self.ModIdentifier} has been staged, please test and merge'),
                    labels=['Needs looking into'],
                )
            return

        self._process_ckan()

    @property
    def delete_attrs(self) -> DeleteMessageBatchRequestEntryTypeDef:
        return {
            'Id': self.message_id,
            'ReceiptHandle': self.receipt_handle
        }


class MessageHandler(BaseMessageHandler):
    primary: Deque[CkanMessage]
    staged: Deque[CkanMessage]

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.primary = deque()
        self.staged = deque()

    def __str__(self) -> str:
        return str(' '.join([str(x) for x in self.primary + self.staged]))

    def __len__(self) -> int:
        return len(self.primary + self.staged)

    @property
    def repo(self) -> CkanMetaRepo:
        return self.game.ckanmeta_repo

    @property
    def github_pr(self) -> GitHubPR:
        return self.game.github_pr

    def append(self, message: Message) -> None:
        ckan = CkanMessage(
            message,
            self.repo,
            self.github_pr
        )
        if not ckan.Staged:
            self.primary.append(ckan)
        else:
            self.staged.append(ckan)

    def _process_queue(self, queue: Deque[CkanMessage]) -> List[CkanMessage]:
        processed = []
        while queue:
            ckan = queue.popleft()
            ckan.process_ckan()
            processed.append(ckan)
        return processed

    # Currently we intermingle Staged/Primary commits
    # separating them out will be a little more efficient
    # with our push/pull traffic.
    def process_messages(self) -> List[DeleteMessageBatchRequestEntryTypeDef]:
        processed = self._process_queue(self.primary)
        if any(ckan.indexed for ckan in processed):
            self.repo.pull_remote_primary()
            self.repo.push_remote_primary()
        processed.extend(self._process_queue(self.staged))
        return [c.delete_attrs for c in processed]


class IndexerQueueHandler(QueueHandler):
    _handler_class: Type[BaseMessageHandler] = MessageHandler
