import shutil
import tempfile
import unittest
from pathlib import Path, PurePath

from git import Repo
from gitdb.exc import BadName
from netkan.repos import NetkanRepo, CkanMetaRepo


class TestRepo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        super(TestRepo, cls).setUpClass()
        cls.tmpdir = tempfile.TemporaryDirectory()
        cls.working = Path(cls.tmpdir.name, 'working')
        upstream = Path(cls.tmpdir.name, 'upstream')
        upstream.mkdir()
        Repo.init(upstream, bare=True)
        shutil.copytree(cls.test_data, cls.working)
        cls.repo = Repo.init(cls.working)
        cls.repo.index.add(cls.repo.untracked_files)
        cls.repo.index.commit('Test Data')
        cls.repo.create_remote('origin', upstream.as_posix())
        cls.repo.remotes.origin.push('master:master')

    @classmethod
    def tearDownClass(cls):
        super(TestRepo, cls).tearDownClass()
        cls.tmpdir.cleanup()

    def tearDown(self):
        meta = self.repo
        meta.git.clean('-df')
        meta.heads.master.checkout()
        try:
            cleanup = meta.create_head('cleanup', 'HEAD~1')
            meta.head.reference = cleanup
            meta.head.reset(index=True, working_tree=True)
        except BadName:
            pass


class TestNetkanRepo(TestRepo):
    test_data = Path(PurePath(__file__).parent, 'testdata/NetKAN')

    def setUp(self):
        self.nk_repo = NetkanRepo(self.repo)

    def test_nk_path(self):
        self.assertTrue(self.nk_repo.nk_path('DogeCoinFlag').exists())

    def test_active_branch(self):
        self.assertEqual(self.nk_repo.active_branch, 'master')

    def test_is_active_branch(self):
        self.assertTrue(self.nk_repo.is_active_branch('master'))
        self.assertFalse(self.nk_repo.is_active_branch('some/other/branch'))

    def test_checkout_branch(self):
        self.assertTrue(self.nk_repo.is_active_branch('master'))
        self.nk_repo.checkout_branch('a/branch')
        self.assertTrue(self.nk_repo.is_active_branch('a/branch'))



class TestCkanMetaRepo(TestRepo):
    test_data = Path(PurePath(__file__).parent, 'testdata/CKAN-meta')

    def setUp(self):
        self.ckm_repo = CkanMetaRepo(self.repo)

    def test_mod_path(self):
        self.assertTrue(self.ckm_repo.mod_path('AwesomeMod').exists())
