import unittest
from pathlib import Path, PurePath

from git import Repo
from netkan.repos import NetkanRepo, CkanMetaRepo


class TestNetkanRepo(unittest.TestCase):
    nk_repo = NetkanRepo(Repo(Path(PurePath(__file__).parent, 'testdata/NetKAN')))

    def test_nk_path(self):
        self.assertTrue(self.nk_repo.nk_path('DogeCoinFlag').exists())


class TestCkanMetaRepo(unittest.TestCase):
    ckm_repo = CkanMetaRepo(Repo(Path(PurePath(__file__).parent, 'testdata/CKAN-meta')))

    def test_mod_path(self):
        self.assertTrue(self.ckm_repo.mod_path('AwesomeMod').exists())
