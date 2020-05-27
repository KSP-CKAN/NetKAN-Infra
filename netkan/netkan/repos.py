import logging
from pathlib import Path
from git import Repo

from .metadata import Netkan, Ckan, CkanGroup


class NetkanRepo:

    """
    Encapsulates all assumptions we make about the structure of NetKAN
    """

    NETKAN_DIR = 'NetKAN'
    UNFROZEN_SUFFIX = 'netkan'
    FROZEN_SUFFIX = 'frozen'
    NETKAN_GLOB = f'**/*.{UNFROZEN_SUFFIX}'

    def __init__(self, git_repo):
        self.git_repo = git_repo
        self.nk_dir = Path(self.git_repo.working_dir, self.NETKAN_DIR)

    def nk_path(self, identifier):
        return self.nk_dir.joinpath(f'{identifier}.{self.UNFROZEN_SUFFIX}')

    def frozen_path(self, identifier):
        return self.nk_dir.joinpath(f'{identifier}.{self.FROZEN_SUFFIX}')

    def all_nk_paths(self):
        return sorted(self.nk_dir.glob(self.NETKAN_GLOB),
                      key=self._nk_sort)

    def nk_paths(self, identifiers):
        return (self.nk_path(identifier) for identifier in identifiers)

    def netkans(self):
        return (Netkan(f) for f in self.all_nk_paths())

    def _nk_sort(self, p):
        return p.stem.casefold()


class CkanMetaRepo:

    """
    Encapsulates all assumptions we make about the structure of CKAN-meta
    """

    CKANMETA_GLOB = '**/*.ckan'

    def __init__(self, git_repo):
        self.git_repo = git_repo
        self.ckm_dir = Path(self.git_repo.working_dir)

    def mod_path(self, identifier):
        return self.ckm_dir.joinpath(identifier)

    def ckans(self, identifier):
        return (Ckan(p) for p in self.mod_path(identifier).glob(self.CKANMETA_GLOB))

    def group(self, identifier):
        return CkanGroup(self, identifier)
