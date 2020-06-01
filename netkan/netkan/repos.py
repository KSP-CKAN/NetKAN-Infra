import logging
from pathlib import Path
from typing import Iterable, List, Optional

from git import Repo, Commit
from .metadata import Netkan, Ckan

class XkanRepo:

    """
    Concantenates all common repo operations in one place
    """

    def __init__(self, git_repo: Repo) -> None:
        self.git_repo = git_repo

    def commit(self, files: List[str], commit_message: str) -> Commit:
        index = self.git_repo.index
        index.add(files)
        return index.commit(commit_message)


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

    def _nk_sort(self, path: Path) -> str:
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
