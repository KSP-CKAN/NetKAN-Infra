import sys
import logging
from pathlib import Path
from typing import Union, Callable, Any, Optional

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
    click.option('--ssh-key', envvar='SSH_KEY', expose_value=False,
                 help='SSH key for accessing repositories', callback=ctx_callback),
    click.option('--deep-clone', is_flag=True, default=False, expose_value=False,
                 help='Perform a deep clone of the git repos', callback=ctx_callback),
    click.option('--ckanmeta-remote', envvar='CKANMETA_REMOTE', expose_value=False,
                 help='game=Path/URL/SSH to Metadata Repos, ie ksp=http://gihub.com',
                 multiple=True, callback=ctx_callback),
    click.option('--netkan-remote', envvar='NETKAN_REMOTE', expose_value=False,
                 help='game=Path/URL/SSH to the Stub Metadata Repos, ie ksp=git@github.com',
                 multiple=True, callback=ctx_callback),
    click.option('--token', envvar='GH_Token', expose_value=False,
                 help='GitHub Token for PRs', callback=ctx_callback),
    click.option('--repo', envvar='CKAN_REPO', expose_value=False,
                 help='GitHub repo to raise PR against (Org Repo: CKAN-meta/NetKAN)',
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
    click.option('--ia-collection', envvar='IA_collection', expose_value=False,
                 help='game=Collection, for mirroring mods in on Internet Archive',
                 multiple=True, callback=ctx_callback),
]


class Game:
    name: str
    shared: 'SharedArgs'
    _ckanmeta_repo: CkanMetaRepo
    _ckanmeta_remote: str
    _netkan_repo: NetkanRepo
    _netkan_remote: str
    _github_pr: GitHubPR

    def __init__(self, name: str, shared: 'SharedArgs') -> None:
        self.name = name
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

    @property
    def ckanmeta_repo(self) -> CkanMetaRepo:
        if getattr(self, '_ckanmeta_repo', None) is None:
            self._ckanmeta_repo = CkanMetaRepo(
                init_repo(self.ckanmeta_remote, '/tmp/CKAN-meta', self.shared.deep_clone))
        return self._ckanmeta_repo

    @property
    def ckanmeta_remote(self) -> str:
        if getattr(self, '_ckanmeta_remote', None) is None:
            self._ckanmeta_remote = self.args('ckanmeta_remote')
        return self._ckanmeta_remote

    @property
    def netkan_repo(self) -> NetkanRepo:
        if getattr(self, '_netkan_repo', None) is None:
            self._netkan_repo = NetkanRepo(
                init_repo(self.netkan_remote, '/tmp/NetKAN', self.shared.deep_clone))
        return self._netkan_repo

    @property
    def netkan_remote(self) -> str:
        if getattr(self, '_netkan_remote', None) is None:
            self._netkan_remote = self.args('netkan_remote')
        return self._netkan_remote

    @property
    def github_pr(self) -> GitHubPR:
        if getattr(self, '_github_pr', None) is None:
            self._github_pr = GitHubPR(
                self.shared.token, self.args('repo'), self.shared.user)
        return self._github_pr


class SharedArgs:
    ckanmeta_remote: str
    deep_clone: bool
    dev: bool
    netkan_remote: str
    queue: str
    repo: str
    timeout: int
    token: str
    user: str
    _debug: bool
    _ssh_key: str

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
        init_ssh(value, Path(Path.home(), '.ssh'))
        self._ssh_key = value

    def game(self, game: str) -> Game:
        if getattr(self, f'_game_{game}', None) is None:
            setattr(self, f'_game_{game}', Game(game, self))
        return getattr(self, f'_game_{game}')


pass_state = click.make_pass_decorator(
    SharedArgs, ensure=True)  # pylint: disable=invalid-name


def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    for option in reversed(_COMMON_OPTIONS):
        func = option(func)
    return func
