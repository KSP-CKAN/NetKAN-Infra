import json
import re
import io
from importlib.resources import read_text
from string import Template
from collections import defaultdict, deque
import logging
from typing import Dict, Deque, Any, List, Optional, Type, TYPE_CHECKING
import git
from ruamel.yaml import YAML

from .github_pr import GitHubPR
from .mod_analyzer import ModAnalyzer
from .common import BaseMessageHandler, QueueHandler
from .repos import NetkanRepo

if TYPE_CHECKING:
    from mypy_boto3_sqs.service_resource import Message
    from mypy_boto3_sqs.type_defs import DeleteMessageBatchRequestEntryTypeDef
else:
    Message = object
    DeleteMessageBatchRequestEntryTypeDef = object


# https://github.com/KSP-SpaceDock/SpaceDock/blob/master/KerbalStuff/ckan.py
class SpaceDockAdder:
    PR_BODY_TEMPLATE = Template(read_text('netkan', 'pr_body_template.md'))
    USER_TEMPLATE = Template('[$username]($user_url)')
    _info: Dict[str, Any]

    def __init__(self, message: Message, nk_repo: NetkanRepo, github_pr: Optional[GitHubPR] = None) -> None:
        self.message = message
        self.nk_repo = nk_repo
        self.github_pr = github_pr
        self.yaml = YAML()
        self.yaml.indent(mapping=2, sequence=4, offset=2)

    def __str__(self) -> str:
        return f"{self.info.get('name', '')}"

    @property
    def info(self) -> Dict[str, Any]:
        if getattr(self, '_info', None) is None:
            self._info = json.loads(self.message.body)
        return self._info

    def try_add(self) -> bool:
        netkan = self.make_netkan(self.info)

        # Create .netkan file or quit if already there
        netkan_path = self.nk_repo.nk_path(netkan.get('identifier', ''))
        if netkan_path.exists():
            # Already exists, we are done
            return True

        # Create branch
        branch_name = f"add/{netkan.get('identifier')}"
        try:
            self.nk_repo.git_repo.remotes.origin.fetch(branch_name)
        except git.GitCommandError:
            # *Shrug*
            pass
        if branch_name not in self.nk_repo.git_repo.heads:
            self.nk_repo.git_repo.create_head(
                branch_name,
                getattr(  # type: ignore[arg-type]
                    self.nk_repo.git_repo.remotes.origin.refs,
                    branch_name,
                    self.nk_repo.git_repo.remotes.origin.refs.master
                )
            )
        # Checkout branch
        self.nk_repo.git_repo.heads[branch_name].checkout()

        # Create file
        netkan_path.write_text(self.yaml_dump(netkan))

        # Add netkan to branch
        self.nk_repo.git_repo.index.add([netkan_path.as_posix()])

        # Commit
        self.nk_repo.git_repo.index.commit(
            (
                f"Add {self.info.get('name')} from {self.info.get('site_name')}"
                f"\n\nThis is an automated commit on behalf of {self.info.get('username')}"
            ),
            author=git.Actor(self.info.get('username'), self.info.get('email'))
        )

        # Push branch
        self.nk_repo.git_repo.remotes.origin.push(
            '{mod}:{mod}'.format(mod=branch_name))

        # Create pull request
        if self.github_pr:
            self.github_pr.create_pull_request(
                title=f"Add {self.info.get('name')} from {self.info.get('site_name')}",
                branch=branch_name,
                body=self.PR_BODY_TEMPLATE.safe_substitute(
                    defaultdict(lambda: '', self.info)),
                labels=['Pull request', 'Mod-request'],
            )
        return True

    @staticmethod
    def _pr_body(info: Dict[str, Any]) -> str:
        return SpaceDockAdder.PR_BODY_TEMPLATE.safe_substitute(
            defaultdict(lambda: '',
                        {**info,
                         'all_authors_md': ', '.join(SpaceDockAdder.USER_TEMPLATE.safe_substitute(defaultdict(lambda: '', a))
                                                     for a in [info, *info.get('shared_authors', [])])}))

    def yaml_dump(self, obj: Dict[str, Any]) -> str:
        sio = io.StringIO()
        self.yaml.dump(obj, sio)
        return sio.getvalue()

    @staticmethod
    def sd_download_url(info: Dict[str, Any]) -> str:
        return f"https://spacedock.info/mod/{info.get('id', '')}/{info.get('name', '')}/download"

    @classmethod
    def make_netkan(cls, info: Dict[str, Any]) -> Dict[str, Any]:
        ident = re.sub(r'[\W_]+', '', info.get('name', ''))
        mod: Optional[ModAnalyzer] = None
        props: Dict[str, Any] = {}
        url = SpaceDockAdder.sd_download_url(info)
        try:
            mod = ModAnalyzer(ident, url)
            props = mod.get_netkan_properties() if mod else {}
        except Exception as exc:  # pylint: disable=broad-except
            # Tell Discord about the problem and move on
            logging.error('%s failed to analyze %s from %s',
                          cls.__name__, ident, url, exc_info=exc)
        return {
            'spec_version': 'v1.18',
            'identifier': ident,
            '$kref': f"#/ckan/spacedock/{info.get('id', '')}",
            'license': info.get('license', '').strip().replace(' ', '-'),
            **(props),
            'x_via': f"Automated {info.get('site_name')} CKAN submission"
        }

    @property
    def delete_attrs(self) -> DeleteMessageBatchRequestEntryTypeDef:
        return {
            'Id': self.message.message_id,
            'ReceiptHandle': self.message.receipt_handle
        }


class SpaceDockMessageHandler(BaseMessageHandler):
    _queued: Deque[SpaceDockAdder]
    _processed: List[SpaceDockAdder]

    def __str__(self) -> str:
        return str(' '.join([str(x) for x in self.queued]))

    def __len__(self) -> int:
        return len(self.queued)

    @property
    def repo(self) -> NetkanRepo:
        return self.game.netkan_repo

    @property
    def github_pr(self) -> GitHubPR:
        return self.game.github_pr

    @property
    def queued(self) -> Deque[SpaceDockAdder]:
        if getattr(self, '_queued', None) is None:
            self._queued = deque()
        return self._queued

    @property
    def processed(self) -> List[SpaceDockAdder]:
        if getattr(self, '_processed', None) is None:
            self._processed = []
        return self._processed

    def append(self, message: Message) -> None:
        netkan = SpaceDockAdder(
            message,
            self.repo,
            self.github_pr
        )
        self.queued.append(netkan)

    def _process_queue(self, queue: Deque[SpaceDockAdder]) -> None:
        while queue:
            netkan = queue.popleft()
            if netkan.try_add():
                self.processed.append(netkan)

    def sqs_delete_entries(self) -> List[DeleteMessageBatchRequestEntryTypeDef]:
        return [c.delete_attrs for c in self.processed]

    def process_messages(self) -> None:
        self._process_queue(self.queued)


class SpaceDockAdderQueueHandler(QueueHandler):
    _handler_class: Type[BaseMessageHandler] = SpaceDockMessageHandler
