from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, List, Optional, Generator, Union

from git import Repo, Commit, GitCommandError
from .metadata import Netkan, Ckan


class XkanRepo:

    """
    Concantenates all common repo operations in one place
    """

    def __init__(self, git_repo: Repo) -> None:
        self.git_repo = git_repo

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__}({self.git_repo.__repr__()})>'

    def commit(self, files: List[Union[str, Path]], commit_message: str) -> Commit:
        index = self.git_repo.index
        index.add([x.as_posix() if isinstance(x, Path) else x for x in files])
        return index.commit(commit_message)

    @property
    def active_branch(self) -> str:
        return str(self.git_repo.active_branch)

    def is_active_branch(self, branch_name: str) -> bool:
        return branch_name == self.active_branch

    def checkout_branch(self, branch_name: str) -> None:
        """Checkout Existing Branch

        We utilise this function to checkout a existing branches, though
        it doesn't quite mirror what Git will do directly. If the branch
        doesn't exist an 'AttributeError' will be thown.

        repo.checkout_branch('master')
        """
        branch = getattr(self.git_repo.heads, branch_name)
        branch.checkout()

    def pull_remote_branch(self, branch_name: str, strategy_option: str = 'ours') -> None:
        self.git_repo.remotes.origin.pull(branch_name, strategy_option=strategy_option)

    def push_remote_branch(self, branch_name: str) -> None:
        self.git_repo.remotes.origin.push(branch_name)

    def close_repo(self) -> None:
        self.git_repo.close()

    @contextmanager
    def change_branch(self, branch_name: str) -> Generator[None, None, None]:
        """Change branch and return on exit of context

        For example:
        with ckm.change_branch('test'):
            ckm.commit('/path/to/new_file.ckan', 'commit in branch test')

        Commit will occur in the 'test' branch, which is first created locally, on exit
        of the context it will then push the branch to the remote and change back to
        the previous active branch.
        """
        active_branch = self.active_branch
        try:
            self.git_repo.remotes.origin.fetch(branch_name)
            if branch_name not in self.git_repo.heads:
                self.git_repo.create_head(
                    branch_name,
                    getattr(
                        self.git_repo.remotes.origin.refs,
                        branch_name
                    )
                )
            branch = getattr(
                self.git_repo.heads, branch_name
            )
            branch.checkout()
        except GitCommandError:
            if branch_name not in self.git_repo.heads:
                branch = self.git_repo.create_head(branch_name)
            else:
                branch = getattr(
                    self.git_repo.heads, branch_name
                )
            branch.checkout()
        try:
            yield
        finally:
            # It's unlikely will hit a scenario where the metadata has
            # changed upstream of us, but the bot should win if it does.
            try:
                self.git_repo.remotes.origin.pull(
                    branch_name, strategy_option='ours'
                )
            except GitCommandError:
                pass
            self.git_repo.remotes.origin.push(
                f'{branch_name}:{branch_name}'
            )
            self.checkout_branch(active_branch)


class NetkanRepo(XkanRepo):

    """
    Encapsulates all assumptions we make about the structure of NetKAN
    """

    NETKAN_DIR = 'NetKAN'
    UNFROZEN_SUFFIX = 'netkan'
    FROZEN_SUFFIX = 'frozen'
    NETKAN_GLOB = f'**/*.{UNFROZEN_SUFFIX}'

    @property
    def nk_dir(self) -> Path:
        return Path(self.git_repo.working_dir, self.NETKAN_DIR)

    def nk_path(self, identifier: str) -> Path:
        return self.nk_dir.joinpath(f'{identifier}.{self.UNFROZEN_SUFFIX}')

    def frozen_path(self, identifier: str) -> Path:
        return self.nk_dir.joinpath(f'{identifier}.{self.FROZEN_SUFFIX}')

    def all_nk_paths(self) -> Iterable[Path]:
        return sorted(self.nk_dir.glob(self.NETKAN_GLOB),
                      key=self._nk_sort)

    def nk_paths(self, identifiers: Iterable[str]) -> Iterable[Path]:
        return (self.nk_path(identifier) for identifier in identifiers)

    def netkans(self) -> Iterable[Netkan]:
        return (Netkan(f) for f in self.all_nk_paths())

    @staticmethod
    def _nk_sort(path: Path) -> str:
        return path.stem.casefold()


class CkanMetaRepo(XkanRepo):

    """
    Encapsulates all assumptions we make about the structure of CKAN-meta
    """

    CKANMETA_GLOB = '**/*.ckan'

    @property
    def ckm_dir(self) -> Path:
        return Path(self.git_repo.working_dir)

    def mod_path(self, identifier: str) -> Path:
        return self.ckm_dir.joinpath(identifier)

    def ckans(self, identifier: str) -> Iterable[Ckan]:
        return (Ckan(f) for f in self.mod_path(identifier).glob(self.CKANMETA_GLOB))

    def highest_version(self, identifier: str) -> Optional[Ckan.Version]:
        highest = max(self.ckans(identifier), default=None, key=lambda ck: ck.version)
        return highest.version if highest else None
