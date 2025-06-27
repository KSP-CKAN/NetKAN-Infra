import sys
import logging
from pathlib import Path
from typing import Union, Callable, Any, List, Optional, Tuple, Dict

import click

from ..repos import NetkanRepo, CkanMetaRepo
from ..utils import init_repo, init_ssh
from ..notifications import setup_log_handler, catch_all
from ..github_pr import GitHubPR


def ctx_callback(ctx: click.Context, param: click.Parameter,
                 value: Union[str, int]) -> Union[str, int]:
    shared = ctx.ensure_object(SharedArgs)
    if param.name:
        setattr(shared, param.name, value)
    return value


_COMMON_OPTIONS = [
    click.option('--debug', is_flag=True, default=False, expose_value=False,
                 help='Enable debug logging', callback=ctx_callback),
    click.option('--queue', envvar='SQS_QUEUE', expose_value=False,
                 help='SQS Queue to poll for metadata', callback=ctx_callback),
    click.option('--inflation-queues', envvar='INFLATION_QUEUES', expose_value=False,
                 help='SQS Queues to publish inflation tasks', multiple=True,
                 callback=ctx_callback),
    click.option('--ssh-key', envvar='SSH_KEY', expose_value=False,
                 help='SSH key for accessing repositories', callback=ctx_callback),
    click.option('--deep-clone', is_flag=True, default=False, expose_value=False,
                 help='Perform a deep clone of the git repos', callback=ctx_callback),
    click.option('--ckanmeta-remotes', envvar='CKANMETA_REMOTES', expose_value=False,
                 help='game=Path/URL/SSH to Metadata Repos, ie ksp=http://github.com',
                 multiple=True, callback=ctx_callback),
    click.option('--netkan-remotes', envvar='NETKAN_REMOTES', expose_value=False,
                 help='game=Path/URL/SSH to the Stub Metadata Repos, ie ksp=git@github.com',
                 multiple=True, callback=ctx_callback),
    click.option('--token', envvar='GH_Token', expose_value=False,
                 help='GitHub Token for PRs', callback=ctx_callback),
    click.option('--repos', envvar='CKAN_REPOS', expose_value=False,
                 help='GitHub repos to raise PR against (Org Repo: ksp=CKAN-meta/NetKAN)',
                 multiple=True, callback=ctx_callback),
    click.option('--user', envvar='CKAN_USER', expose_value=False,
                 help='GitHub user/org repo resides under (Org User: KSP-CKAN)',
                 callback=ctx_callback),
    click.option('--timeout', default=300, envvar='SQS_TIMEOUT', expose_value=False,
                 help='Reduce message visibility timeout for testing', callback=ctx_callback),
    click.option('--dev', is_flag=True, default=False, expose_value=False,
                 help='Disable Production Checks', callback=ctx_callback),
    click.option('--ia-access', envvar='IA_access', expose_value=False,
                 help='Credentials for Internet Archive', callback=ctx_callback),
    click.option('--ia-secret', envvar='IA_secret', expose_value=False,
                 help='Credentials for Internet Archive', callback=ctx_callback),
    click.option('--ia-collections', envvar='IA_COLLECTIONS', expose_value=False,
                 help='game=Collection, for mirroring mods in on Internet Archive',
                 multiple=True, callback=ctx_callback),
    click.option('--game-id', default='KSP', envvar='GAME_ID', help='Game ID for this task',
                 expose_value=False, callback=ctx_callback)
]


class Game:
    name: str
    shared: 'SharedArgs'
    clone_base: str = '/tmp'
    _ckanmeta_repo: CkanMetaRepo
    _ckanmeta_remote: str
    _netkan_repo: NetkanRepo
    _netkan_remote: str
    _github_pr: GitHubPR
    _ia_collection: str
    _inflation_queue: str
    MOD_ROOTS: Dict[str, str] = {
        'ksp':  'GameData',
        'ksp2': 'BepInEx/plugins',
    }

    def __init__(self, name: str, shared: 'SharedArgs') -> None:
        self.name = name.lower()
        self.shared = shared

    def args(self, arg: str) -> str:
        result = None
        try:
            result = [x.split('=')[1] for x in getattr(
                self.shared, arg) if x.split('=')[0] == self.name][0]
        except IndexError:
            pass
        if result is None:
            logging.fatal(
                "Expecting attribute '%s' to be set for '%s'; exiting disgracefully!",
                arg, self.name
            )
            sys.exit(1)
        return result

    def repo_base_path(self, path: str) -> str:
        return f'{self.clone_base}/{self.name}/{path}'

    @property
    def ckanmeta_repo(self) -> CkanMetaRepo:
        if getattr(self, '_ckanmeta_repo', None) is None:
            self._ckanmeta_repo = CkanMetaRepo(
                init_repo(
                    self.ckanmeta_remote,
                    self.repo_base_path('CKAN-meta'),
                    self.shared.deep_clone
                ),
                game_id=self.name
            )
        return self._ckanmeta_repo

    @property
    def ckanmeta_remote(self) -> str:
        if getattr(self, '_ckanmeta_remote', None) is None:
            self._ckanmeta_remote = self.args('ckanmeta_remotes')
        return self._ckanmeta_remote

    @property
    def netkan_repo(self) -> NetkanRepo:
        if getattr(self, '_netkan_repo', None) is None:
            self._netkan_repo = NetkanRepo(
                init_repo(
                    self.netkan_remote,
                    self.repo_base_path('NetKAN'),
                    self.shared.deep_clone
                ),
                game_id=self.name
            )
        return self._netkan_repo

    @property
    def repos(self) -> List[Union[NetkanRepo, CkanMetaRepo]]:
        return [self.ckanmeta_repo, self.netkan_repo]

    @property
    def netkan_remote(self) -> str:
        if getattr(self, '_netkan_remote', None) is None:
            self._netkan_remote = self.args('netkan_remotes')
        return self._netkan_remote

    @property
    def github_pr(self) -> GitHubPR:
        if getattr(self, '_github_pr', None) is None:
            self._github_pr = GitHubPR(
                self.shared.token, self.args('repos'), self.shared.user)
        return self._github_pr

    @property
    def ia_collection(self) -> str:
        if getattr(self, '_ia_collection', None) is None:
            self._ia_collection = self.args('ia_collections')
        return self._ia_collection

    @property
    def inflation_queue(self) -> str:
        if getattr(self, '_inflation_queue', None) is None:
            self._inflation_queue = self.args('inflation_queues')
        return self._inflation_queue

    @property
    def mod_root(self) -> str:
        return self.MOD_ROOTS[self.name]


class SharedArgs:
    ckanmeta_remotes: Tuple[str, ...]
    deep_clone: bool
    dev: bool
    game_id: str
    inflation_queues: Tuple[str, ...]
    netkan_remotes: Tuple[str, ...]
    queue: str
    ia_access: str
    ia_secret: str
    ia_collections: Tuple[str, ...]
    repos: Tuple[str, ...]
    timeout: int
    token: str
    user: str
    _debug: bool
    _ssh_key: str
    _game_ids: List[str]

    def __init__(self) -> None:
        self._environment_data = None

    def __getattribute__(self, name: str) -> Any:
        attr = None
        try:
            attr = super().__getattribute__(name)
        except AttributeError:
            pass
        if not name.startswith('_') and attr is None:
            logging.fatal(
                "Expecting attribute '%s' to be set; exiting disgracefully!", name)
            sys.exit(1)
        return attr

    @property
    def debug(self) -> Optional[bool]:
        return self._debug

    @debug.setter
    def debug(self, value: bool) -> None:
        # When there isn't a flag passed we get a None instead, setting
        # it as a 'False' for consistency.
        self._debug = value or False
        # Attempt to set up Discord logger so we can see errors
        if setup_log_handler(self._debug):
            # Catch uncaught exceptions and log them
            sys.excepthook = catch_all

    @property
    def ssh_key(self) -> Optional[str]:
        return self._ssh_key

    @ssh_key.setter
    def ssh_key(self, value: str) -> None:
        if value:
            init_ssh(value, Path(Path.home(), '.ssh'))
        self._ssh_key = value

    def game(self, game: str) -> Game:
        game_id = game.lower()
        if getattr(self, f'_game_{game_id}', None) is None:
            setattr(self, f'_game_{game_id}', Game(game_id, self))
        return getattr(self, f'_game_{game_id}')

    @property
    def game_ids(self) -> List[str]:
        if getattr(self, '_game_ids', None) is None:
            game_ids = set()
            for arg in ['ckanmeta_remotes', 'netkan_remotes', 'ia_collections', 'repos']:
                if arg not in vars(self):
                    continue
                game_ids.update([x.split('=', maxsplit=1)[0]
                                 for x in getattr(self, arg)])
            self._game_ids = sorted(game_ids)  # sorts + casts to list type
        return self._game_ids


pass_state = click.make_pass_decorator(
    SharedArgs, ensure=True)  # pylint: disable=invalid-name


def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    for option in reversed(_COMMON_OPTIONS):
        func = option(func)
    return func
