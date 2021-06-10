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
                 help='Path/URL/SSH to Metadata Repo', callback=ctx_callback),
    click.option('--netkan-remote', envvar='NETKAN_REMOTE', expose_value=False,
                 help='Path/URL/SSH to the Stub Metadata Repo', callback=ctx_callback),
    click.option('--token', envvar='GH_Token', expose_value=False,
                 help='GitHub Token for PRs', callback=ctx_callback),
    click.option('--repo', envvar='CKAN_REPO', expose_value=False,
                 help='GitHub repo to raise PR against (Org Repo: CKAN-meta/NetKAN)',
                 callback=ctx_callback),
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
                 help='Collection to put mirrored mods in on Internet Archive',
                 callback=ctx_callback),
]


class SharedArgs:

    def __init__(self) -> None:
        self._environment_data = None
        self._debug: Optional[bool] = None
        self._ssh_key: Optional[str] = None
        self._ckanmeta_repo: Optional[CkanMetaRepo] = None
        self._netkan_repo: Optional[NetkanRepo] = None
        self._github_pr: Optional[GitHubPR] = None

    def __getattribute__(self, name: str) -> Any:
        attr = super().__getattribute__(name)
        if not name.startswith('_') and attr is None:
            logging.fatal("Expecting attribute '%s' to be set; exiting disgracefully!", name)
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

    @property
    def ckanmeta_repo(self) -> CkanMetaRepo:
        if not self._ckanmeta_repo:
            self._ckanmeta_repo = CkanMetaRepo(
                init_repo(self._ckanmeta_remote, '/tmp/CKAN-meta', self.deep_clone))
        return self._ckanmeta_repo

    @property
    def ckanmeta_remote(self) -> str:
        return self._ckanmeta_remote

    @ckanmeta_remote.setter
    def ckanmeta_remote(self, value: str) -> None:
        self._ckanmeta_remote = value

    @property
    def netkan_repo(self) -> NetkanRepo:
        if not self._netkan_repo:
            self._netkan_repo = NetkanRepo(
                init_repo(self._netkan_remote, '/tmp/NetKAN', self.deep_clone))
        return self._netkan_repo

    @property
    def netkan_remote(self) -> str:
        return self._netkan_remote

    @netkan_remote.setter
    def netkan_remote(self, value: str) -> None:
        self._netkan_remote = value

    @property
    def github_pr(self) -> GitHubPR:
        if not self._github_pr:
            self._github_pr = GitHubPR(self.token, self.repo, self.user)
        return self._github_pr


pass_state = click.make_pass_decorator(SharedArgs, ensure=True)  # pylint: disable=invalid-name


def common_options(func: Callable[..., Any]) -> Callable[..., Any]:
    for option in reversed(_COMMON_OPTIONS):
        func = option(func)
    return func
