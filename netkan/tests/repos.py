import shutil
import tempfile
import unittest
from pathlib import Path, PurePath

from git import Repo
from netkan.repos import NetkanRepo, CkanMetaRepo


class TestRepo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestRepo, cls).setUpClass()
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.working = Path(cls.tmpdir.name, 'working')
        shutil.copytree(cls.test_data, cls.working)

    @classmethod
    def tearDownClass(cls):
        super(TestRepo, cls).tearDownClass()
        cls.tmpdir.cleanup()


class TestNetkanRepo(TestRepo):
    test_data = Path(PurePath(__file__).parent, 'testdata/NetKAN')

    def setUp(self):
        self.nk_repo = NetkanRepo(Repo.init(self.working))

    def test_nk_path(self):
        self.assertTrue(self.nk_repo.nk_path('DogeCoinFlag').exists())


class TestCkanMetaRepo(TestRepo):
    test_data = Path(PurePath(__file__).parent, 'testdata/CKAN-meta')

    def setUp(self):
        self.ckm_repo = CkanMetaRepo(Repo.init(self.working))

    def test_mod_path(self):
        self.assertTrue(self.ckm_repo.mod_path('AwesomeMod').exists())
