import json
import re
import io
from string import Template
from collections import defaultdict, deque
import logging
from typing import Dict, Deque, Any, List, Optional, Type, TYPE_CHECKING
import urllib.parse
import git
from ruamel.yaml import YAML
from github.Repository import Repository
from github import Github

from .cli.common import Game
from .github_pr import GitHubPR
from .mod_analyzer import ModAnalyzer
from .queue_handler import BaseMessageHandler, QueueHandler
from .repos import NetkanRepo
from .utils import legacy_read_text

if TYPE_CHECKING:
    from mypy_boto3_sqs.service_resource import Message
    from mypy_boto3_sqs.type_defs import DeleteMessageBatchRequestEntryTypeDef
else:
    Message = object
    DeleteMessageBatchRequestEntryTypeDef = object


# https://github.com/KSP-SpaceDock/SpaceDock/blob/master/KerbalStuff/ckan.py
class SpaceDockAdder:
    COMMIT_TEMPLATE = Template(legacy_read_text('netkan', 'sd_adder_commit_template.md'))
    PR_BODY_TEMPLATE = Template(legacy_read_text('netkan', 'sd_adder_pr_body_template.md'))
    USER_TEMPLATE = Template('[$username]($user_url)')
    TITLE_TEMPLATE = Template('Add $name from $site_name')
    GITHUB_PATH_PATTERN = re.compile(r'^/([^/]+)/([^/]+)')
    _info: Dict[str, Any]

    def __init__(self, message: Message, nk_repo: NetkanRepo,
                 game: Game, github_pr: GitHubPR) -> None:
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
        ident = netkan[0].get('identifier', '')

        # Create .netkan file or quit if already there
        netkan_path = self.nk_repo.nk_path(ident)
        if netkan_path.exists():
            # Already exists, we are done
            return True

        if self.nk_repo.frozen_path(ident).exists():
            # Already frozen, quit
            return True

        # Create and checkout branch
        branch_name = f"add/{netkan[0].get('identifier')}"
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
        try:
            return SpaceDockAdder.PR_BODY_TEMPLATE.safe_substitute(defaultdict(
                lambda: '',
                {**info,
                 'all_authors_md': ', '.join(SpaceDockAdder.USER_TEMPLATE.safe_substitute(
                                                                defaultdict(lambda: '', a))
                                             for a in info.get('all_authors', []))}))
        except Exception as exc:
            # Log the input on failure
            logging.error('Failed to generate pull request body from %s', info)
            raise exc

    def yaml_dump(self, objs: List[Dict[str, Any]]) -> str:
        sio = io.StringIO()
        self.yaml.dump_all(objs, sio)
        return sio.getvalue()

    @staticmethod
    def sd_download_url(info: Dict[str, Any]) -> str:
        return f"https://spacedock.info/mod/{info.get('id', '')}/{info.get('name', '')}/download"

    def make_netkan(self, info: Dict[str, Any]) -> List[Dict[str, Any]]:
        netkans = []
        ident = re.sub(r'[\W_]+', '', info.get('name', ''))
        gh_repo = self.get_github_repo(info.get('source_link', ''))
        if gh_repo is not None:
            gh_netkan = self.make_github_netkan(ident, gh_repo)
            if gh_netkan is not None:
                netkans.append(gh_netkan)
        netkans.append(self.make_spacedock_netkan(ident, info))
        return netkans

    def make_spacedock_netkan(self, ident: str, info: Dict[str, Any]) -> Dict[str, Any]:
        mod: Optional[ModAnalyzer] = None
        props: Dict[str, Any] = {}
        url = SpaceDockAdder.sd_download_url(info)
        try:
            mod = ModAnalyzer(ident, url, self.game)
            props = mod.get_netkan_properties() if mod else {}
        except Exception as exc: # pylint: disable=broad-except
            # Tell Discord about the problem and move on
            logging.error('%s failed to analyze %s from %s',
                          self.__class__.__name__, ident, url, exc_info=exc)
        vref_props = {'$vref': props.pop('$vref')} if '$vref' in props else {}
        return {
            'identifier': ident,
            '$kref': f"#/ckan/spacedock/{info.get('id', '')}",
            **(vref_props),
            **(props),
            'x_via': f"Automated {info.get('site_name')} CKAN submission"
        }

    def get_github_repo(self, source_link: str) -> Optional[Repository]:
        url_parse = urllib.parse.urlparse(source_link)
        if url_parse.netloc == 'github.com':
            match = self.GITHUB_PATH_PATTERN.match(url_parse.path)
            if match:
                repo_name = '/'.join(match.groups())
                g = Github(self.github_pr.token)
                try:
                    return g.get_repo(repo_name)
                except Exception as exc: # pylint: disable=broad-except
                    # Tell Discord about the problem and move on
                    logging.error('%s failed to get GitHub repo from SpaceDock source url %s',
                                  self.__class__.__name__, source_link, exc_info=exc)
                    return None
        return None

    def make_github_netkan(self, ident: str, gh_repo: Repository) -> Optional[Dict[str, Any]]: # pylint: disable=too-many-locals
        mod: Optional[ModAnalyzer] = None
        props: Dict[str, Any] = {}
        try:
            latest_release = gh_repo.get_latest_release()
        except: # pylint: disable=broad-except,bare-except
            logging.warning('No releases found on GitHub for %s, omitting GitHub section', ident)
            return None
        tag_name = latest_release.tag_name
        digit = re.search(r"\d", tag_name)
        version_find = ''
        if digit:
            version_find = tag_name[:digit.start()]
        assets = latest_release.assets
        use_source_archive = not assets
        url = latest_release.zipball_url if use_source_archive \
                                         else assets[0].browser_download_url
        try:
            mod = ModAnalyzer(ident, url, self.game)
            props = mod.get_netkan_properties() if mod else {}
        except Exception as exc: # pylint: disable=broad-except
            # Tell Discord about the problem and move on
            logging.error('%s failed to analyze %s from %s',
                          self.__class__.__name__, ident, url, exc_info=exc)
        vref_props = {'$vref': props.pop('$vref')} if '$vref' in props else {}
        return {
            'identifier': ident,
            '$kref': f"#/ckan/github/{gh_repo.full_name}",
            **({'x_netkan_github': {'use_source_archive': True}}
               if use_source_archive else {}),
            **({'x_netkan_version_edit': f'^{version_find}?(?<version>.+)$'}
               if version_find != '' else {}),
            **(vref_props),
        }

    @property
    def delete_attrs(self) -> DeleteMessageBatchRequestEntryTypeDef:
        return {
            'Id': self.message.message_id,
            'ReceiptHandle': self.message.receipt_handle
        }


class SpaceDockMessageHandler(BaseMessageHandler):
    queued: Deque[SpaceDockAdder]

    def __init__(self, game: Game) -> None:
        super().__init__(game)
        self.queued = deque()

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

    def _process_queue(self, queue: Deque[SpaceDockAdder]) -> List[SpaceDockAdder]:
        processed = []
        while queue:
            netkan = queue.popleft()
            if netkan.try_add():
                processed.append(netkan)
        return processed

    def process_messages(self) -> List[DeleteMessageBatchRequestEntryTypeDef]:
        return [c.delete_attrs for c in self._process_queue(self.queued)]


class SpaceDockAdderQueueHandler(QueueHandler):
    _handler_class: Type[BaseMessageHandler] = SpaceDockMessageHandler
