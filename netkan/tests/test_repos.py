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
        Repo.init(cls.upstream, bare=True, initial_branch='main')
        shutil.copytree(cls.test_data, cls.working)
        cls.repo = Repo.init(cls.working, initial_branch='main')
        Path(cls.working, '.git', 'HEAD').write_text('ref: refs/heads/main')
        shutil.copy(Path(__file__).parent.parent / '.gitconfig',
                    cls.working / '.git' / 'config')
        cls.repo.index.add(cls.repo.untracked_files)
        cls.repo.index.commit('Test Data')
        cls.repo.create_remote('origin', cls.upstream.as_posix())
        cls.repo.remotes.origin.push('main:main')
        # When we clone at repo access, we use a git clone which
        # sets this automatically.
        cls.repo.git.remote('set-head', 'origin', '-a')

    @classmethod
    def tearDownClass(cls):
        super(TestRepo, cls).tearDownClass()
        cls.tmpdir.cleanup()

    def tearDown(self):
        meta = self.repo
        meta.git.clean('-df')
        meta.heads.main.checkout()
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

    def test_repr(self):
        self.assertEqual(str(self.nk_repo),
                         f'<NetkanRepo({self.nk_repo.git_repo})>')

    def test_nk_path(self):
        self.assertTrue(self.nk_repo.nk_path('DogeCoinFlag').exists())

    def test_nk_frozen_path(self):
        self.assertEqual(
            self.nk_repo.frozen_path('DogeCoinFlag').as_posix(),
            f'{self.nk_repo.git_repo.working_dir}/NetKAN/DogeCoinFlag.frozen'
        )

    def test_active_branch(self):
        self.assertEqual(self.nk_repo.active_branch, 'main')

    def test_primary_active(self):
        self.assertTrue(self.nk_repo.is_primary_active())

    def test_primary_inactive(self):
        with self.nk_repo.change_branch('not/primary'):
            self.assertFalse(self.nk_repo.is_primary_active())

    def test_primary_branch(self):
        self.assertEqual(self.nk_repo.primary_branch, 'main')

    def test_primary_branch_path(self):
        self.assertEqual(self.nk_repo.primary_branch_path, 'refs/heads/main')

    def test_is_active_branch(self):
        self.assertTrue(self.nk_repo.is_active_branch('main'))
        self.assertFalse(self.nk_repo.is_active_branch('some/other/branch'))

    def test_checkout_branch(self):
        with self.nk_repo.change_branch('a/branch'):
            pass
        self.assertTrue(self.nk_repo.is_active_branch('main'))
        self.nk_repo.checkout_branch('a/branch')
        self.assertTrue(self.nk_repo.is_active_branch('a/branch'))

    def test_checkout_primary(self):
        with self.nk_repo.change_branch('not/primary'):
            self.assertFalse(self.nk_repo.is_primary_active())
            self.nk_repo.checkout_primary()
            self.assertTrue(self.nk_repo.is_primary_active())

    def test_primary_push_pull(self):
        new_clone = Repo.init(Path(self.tmpdir.name, 'primary_push_pull'))
        new_clone.create_remote('origin', self.upstream.as_posix())
        Path(new_clone.working_dir, '.git', 'HEAD').write_text(
            'ref: refs/heads/main')
        new_clone.remotes.origin.pull('main')
        new_clone.git.remote('set-head', 'origin', '-a')
        new_repo = NetkanRepo(new_clone)
        new_repo.pull_remote_primary()
        Path(new_repo.nk_dir, 'test_pushpull_file').write_text(
            'I can haz cheezburger')
        new_repo.commit(new_repo.git_repo.untracked_files, 'Pls')
        new_repo.push_remote_primary()
        self.assertFalse(
            Path(self.nk_repo.nk_dir, 'test_pushpull_file').exists())
        self.nk_repo.pull_remote_primary()
        self.assertTrue(
            Path(self.nk_repo.nk_dir, 'test_pushpull_file').exists())

    def test_branch_push_pull(self):
        new_clone = Repo.init(Path(self.tmpdir.name, 'push_pull'))
        new_clone.create_remote('origin', self.upstream.as_posix())
        new_clone.remotes.origin.pull('main')
        new_clone.git.remote('set-head', 'origin', '-a')
        new_repo = NetkanRepo(new_clone)
        with new_repo.change_branch('test/change'):
            pass
        new_repo.checkout_branch('test/change')
        new_repo.pull_remote_branch('test/change')
        Path(new_repo.nk_dir, 'test_pushpull_file').write_text(
            'I can haz cheezburger')
        new_repo.commit(new_repo.git_repo.untracked_files, 'Pls')
        new_repo.push_remote_branch('test/change')
        self.assertFalse(
            Path(self.nk_repo.nk_dir, 'test_pushpull_file').exists())
        with self.nk_repo.change_branch('test/change'):
            self.nk_repo.pull_remote_branch('test/change')
            self.assertTrue(
                Path(self.nk_repo.nk_dir, 'test_pushpull_file').exists())

    def test_change_branch(self):
        self.assertTrue(self.nk_repo.is_primary_active())
        staged = Path(self.nk_repo.nk_dir, 'StagedMod.netkan')
        self.assertFalse(staged.exists())
        with self.nk_repo.change_branch('some/other/branch'):
            self.assertTrue(self.nk_repo.is_active_branch('some/other/branch'))
            staged.write_text('{"name": "Stagey McStage"}')
            self.assertTrue(staged.exists())
            self.nk_repo.commit(self.nk_repo.nk_paths(
                ['StagedMod']), 'Test Stage')
        self.assertFalse(staged.exists())

    def test_create_branch_local(self):
        self.nk_repo.git_repo.create_head('local/test')
        with self.nk_repo.change_branch('local/test'):
            self.assertEqual(self.nk_repo.active_branch, 'local/test')


class TestCkanMetaRepo(TestRepo):
    test_data = Path(PurePath(__file__).parent, 'testdata/CKAN-meta')

    def setUp(self):
        self.ckm_repo = CkanMetaRepo(self.repo)

    def test_mod_path(self):
        self.assertTrue(self.ckm_repo.mod_path('AwesomeMod').exists())

    def test_identifiers(self):
        self.assertListEqual(
            sorted(self.ckm_repo.identifiers()),
            ['AdequateMod', 'AmazingMod', 'AwesomeMod']
        )

    def test_all_latest_modules(self):
        self.assertListEqual(
            sorted([str(x) for x in self.ckm_repo.all_latest_modules()]),
            ['<Ckan(AdequateMod, 1:0.2)>', '<Ckan(AmazingMod, v1.1)>',
             '<Ckan(AwesomeMod, 0.11)>']
        )


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
