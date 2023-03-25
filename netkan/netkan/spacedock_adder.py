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

from .cli.common import Game
from .github_pr import GitHubPR
from .mod_analyzer import ModAnalyzer
from .queue_handler import BaseMessageHandler, QueueHandler
from .repos import NetkanRepo

if TYPE_CHECKING:
    from mypy_boto3_sqs.service_resource import Message
    from mypy_boto3_sqs.type_defs import DeleteMessageBatchRequestEntryTypeDef
else:
    Message = object
    DeleteMessageBatchRequestEntryTypeDef = object


# https://github.com/KSP-SpaceDock/SpaceDock/blob/master/KerbalStuff/ckan.py
class SpaceDockAdder:
    COMMIT_TEMPLATE = Template(read_text('netkan', 'sd_adder_commit_template.md'))
    PR_BODY_TEMPLATE = Template(read_text('netkan', 'sd_adder_pr_body_template.md'))
    USER_TEMPLATE = Template('[$username]($user_url)')
    TITLE_TEMPLATE = Template('Add $name from $site_name')
    _info: Dict[str, Any]

    def __init__(self, message: Message, nk_repo: NetkanRepo, game: Game, github_pr: Optional[GitHubPR] = None) -> None:
        self.message = message
        self.nk_repo = nk_repo
        self.game = game
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

        # Create and checkout branch
        branch_name = f"add/{netkan.get('identifier')}"
        with self.nk_repo.change_branch(branch_name):
            # Create file
            netkan_path.write_text(self.yaml_dump(netkan))

            # Add netkan to branch
            self.nk_repo.git_repo.index.add([netkan_path.as_posix()])

            # Commit
            self.nk_repo.git_repo.index.commit(
                self.COMMIT_TEMPLATE.safe_substitute(
                    defaultdict(lambda: '', self.info)),
                author=git.Actor(self.info.get('username'), self.info.get('email')))

        # Create pull request
        if self.github_pr:
            self.github_pr.create_pull_request(
                title=self.TITLE_TEMPLATE.safe_substitute(defaultdict(lambda: '', self.info)),
                branch=branch_name,
                body=SpaceDockAdder._pr_body(self.info),
                labels=['Mod request'])
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

    def make_netkan(self, info: Dict[str, Any]) -> Dict[str, Any]:
        ident = re.sub(r'[\W_]+', '', info.get('name', ''))
        mod: Optional[ModAnalyzer] = None
        props: Dict[str, Any] = {}
        url = SpaceDockAdder.sd_download_url(info)
        try:
            mod = ModAnalyzer(ident, url, self.game)
            props = mod.get_netkan_properties() if mod else {}
        except Exception as exc:  # pylint: disable=broad-except
            # Tell Discord about the problem and move on
            logging.error('%s failed to analyze %s from %s',
                          self.__class__.__name__, ident, url, exc_info=exc)
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
    queued: Deque[SpaceDockAdder]
    processed: List[SpaceDockAdder]

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.queued = deque()
        self.processed = []

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

    def append(self, message: Message) -> None:
        self.queued.append(
            SpaceDockAdder(message, self.repo, self.game, self.github_pr))

    def _process_queue(self, queue: Deque[SpaceDockAdder]) -> None:
        while queue:
            netkan = queue.popleft()
            if netkan.try_add():
                self.processed.append(netkan)

    def sqs_delete_entries(self) -> List[DeleteMessageBatchRequestEntryTypeDef]:
        entries = [c.delete_attrs for c in self.processed]
        self.processed = []
        return entries

    def process_messages(self) -> None:
        self._process_queue(self.queued)


class SpaceDockAdderQueueHandler(QueueHandler):
    _handler_class: Type[BaseMessageHandler] = SpaceDockMessageHandler
