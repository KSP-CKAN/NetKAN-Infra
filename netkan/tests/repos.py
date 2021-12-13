# pylint: disable-all
# flake8: noqa

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
        cls.upstream = Path(cls.tmpdir.name, 'upstream')
        cls.upstream.mkdir()
        Repo.init(cls.upstream, bare=True)
        shutil.copytree(cls.test_data, cls.working)
        cls.repo = Repo.init(cls.working)
        shutil.copy(Path(__file__).parent.parent / '.gitconfig', cls.working / '.git' / 'config')
        cls.repo.index.add(cls.repo.untracked_files)
        cls.repo.index.commit('Test Data')
        cls.repo.create_remote('origin', cls.upstream.as_posix())
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
        with self.nk_repo.change_branch('a/branch'):
            pass
        self.assertTrue(self.nk_repo.is_active_branch('master'))
        self.nk_repo.checkout_branch('a/branch')
        self.assertTrue(self.nk_repo.is_active_branch('a/branch'))

    def test_push_pull(self):
        new_clone = Repo.init(Path(self.tmpdir.name, 'push_pull'))
        new_clone.create_remote('origin', self.upstream.as_posix())
        new_repo = NetkanRepo(new_clone)
        new_repo.pull_remote_branch('master')
        Path(new_repo.nk_dir, 'test_pushpull_file').write_text('I can haz cheezburger')
        new_repo.commit(new_repo.git_repo.untracked_files, 'Pls')
        new_repo.push_remote_branch('master')
        self.assertFalse(Path(self.nk_repo.nk_dir, 'test_pushpull_file').exists())
        self.nk_repo.pull_remote_branch('master')
        self.assertTrue(Path(self.nk_repo.nk_dir, 'test_pushpull_file').exists())

    def test_change_branch(self):
        self.assertTrue(self.nk_repo.is_active_branch('master'))
        staged = Path(self.nk_repo.nk_dir, 'StagedMod.netkan')
        self.assertFalse(staged.exists())
        with self.nk_repo.change_branch('some/other/branch'):
            self.assertTrue(self.nk_repo.is_active_branch('some/other/branch'))
            staged.write_text('{"name": "Stagey McStage"}')
            self.assertTrue(staged.exists())
            self.nk_repo.commit(self.nk_repo.nk_paths(['StagedMod']), 'Test Stage')
        self.assertFalse(staged.exists())


class TestCkanMetaRepo(TestRepo):
    test_data = Path(PurePath(__file__).parent, 'testdata/CKAN-meta')

    def setUp(self):
        self.ckm_repo = CkanMetaRepo(self.repo)

    def test_mod_path(self):
        self.assertTrue(self.ckm_repo.mod_path('AwesomeMod').exists())


class TestRepoConfig(TestRepo):
    test_data = Path(PurePath(__file__).parent, 'testdata/CKAN-meta')

    def setUp(self):
        self.ckm_repo = CkanMetaRepo(self.repo)

    def test_gc_auto(self):
        self.assertEqual(self.ckm_repo.git_repo.config_reader().get_value('gc','auto'), 2700)

    def test_gc_reflog_expire(self):
        self.assertEqual(self.ckm_repo.git_repo.config_reader().get_value('gc','reflogExpire'), 1)

    def test_gc_worktreePruneExpire(self):
        self.assertEqual(self.ckm_repo.git_repo.config_reader().get_value('gc','worktreePruneExpire'), 'now')

    def test_gc_reflog_expire_unreachable(self):
        self.assertEqual(self.ckm_repo.git_repo.config_reader().get_value('gc','reflogExpireUnreachable'), 'now')

    def test_gc_prune_expire(self):
        self.assertEqual(self.ckm_repo.git_repo.config_reader().get_value('gc','pruneExpire'), 'now')
