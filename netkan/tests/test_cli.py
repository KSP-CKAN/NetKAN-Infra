import sys
from time import time
from os import utime
from pathlib import Path, PurePath
from shutil import copy2
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

from click.testing import CliRunner
from git import Repo

from netkan.cli import clean_cache
from netkan.cli.common import SharedArgs, Game
from netkan.repos import NetkanRepo

from .common import SharedArgsHarness


# This file is intended to test the commands in cli.py, running them directly via click.testing.CliRunner().invoke().
class TestCleanCache(TestCase):

    cache_path = TemporaryDirectory()
    testdata_path = Path(PurePath(__file__).parent, 'testdata/NetKAN/')
    repo = NetkanRepo(Repo.init(testdata_path), 'ksp')

    source_file_1 = repo.nk_path('DogeCoinFlag')
    source_file_2 = repo.nk_path('FlagCoinDoge')
    # Pretend they are zip files.
    target_file_1 = Path(cache_path.name, 'DogeCoinFlag.zip')
    target_file_2 = Path(cache_path.name, 'FlagCoinDoge.zip')

    def setUp(self):

        self.runner = CliRunner()

        copy2(self.source_file_1, self.target_file_1)
        copy2(self.source_file_2, self.target_file_2)

        # 2018-02-06 20:15 UTC, older than 42 days
        utime(self.target_file_1, (1517948100, 1517948100))

        # Make sure the second file has a recent timestamp
        current_time = time()
        utime(self.target_file_2, (current_time, current_time))

    def tearDown(self):

        self.cache_path.cleanup()

    def test_clean_all(self):

        result = self.runner.invoke(
            clean_cache, ['--days', '42', '--cache', self.cache_path.name])

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(Path.exists(self.target_file_1))
        self.assertTrue(Path.exists(self.target_file_2))


class TestSharedArgs(TestCase):

    def test_debug_unset(self):
        shared = SharedArgs()
        with mock.patch.object(sys, 'argv', ['group', 'command']):
            setattr(shared, 'debug', None)
            self.assertFalse(shared.debug)

    def test_shared_unset_arg_exits(self):
        shared = SharedArgs()
        with self.assertRaises(SystemExit) as error:
            shared.ckanmeta_remote  # pylint: disable=pointless-statement
        self.assertEqual(error.exception.code, 1)

    def test_shared_games_none(self):
        shared = SharedArgs()
        self.assertEqual(shared.game_ids, [])

    def test_shared_games_ksp(self):
        shared = SharedArgs()
        shared.ckanmeta_remotes = ('ksp=ckan_url',)
        shared.repos = ('ksp=ckan',)
        self.assertEqual(shared.game_ids, ['ksp'])

    def test_shared_games_ksp2(self):
        shared = SharedArgs()
        shared.ckanmeta_remotes = ('ksp2=ckan_url',)
        shared.repos = ('ksp2=ckan',)
        self.assertEqual(shared.game_ids, ['ksp2'])

    def test_shared_games_multi(self):
        shared = SharedArgs()
        shared.ckanmeta_remotes = ('ksp2=ckan_url', 'ksp=ckan_url')
        shared.repos = ('ksp2=ckan', 'ksp2=ckan')
        self.assertEqual(shared.game_ids, ['ksp', 'ksp2'])


class TestGame(SharedArgsHarness):

    def test_game_unset_var_exits(self):
        game = Game('unknown', self.shared_args)
        with self.assertRaises(SystemExit) as error:
            game.ckanmeta_remote  # pylint: disable=pointless-statement
        self.assertEqual(error.exception.code, 1)

    def test_shared_args_game_ksp(self):
        self.assertEqual(self.shared_args.game('ksp').name, 'ksp')
        self.assertIsInstance(self.shared_args.game('ksp'), Game)

    def test_ckanmeta_remote_ksp(self):
        path = f'{self.tmpdir.name}/upstream/ckan'
        self.assertEqual(
            Game('ksp', self.shared_args).ckanmeta_remote, path)

    def test_netkan_remote_ksp(self):
        path = f'{self.tmpdir.name}/upstream/netkan'
        self.assertEqual(
            Game('ksp', self.shared_args).netkan_remote, path)

    def test_shared_args_game_ksp2(self):
        self.assertEqual(self.shared_args.game('ksp2').name, 'ksp2')
        self.assertIsInstance(self.shared_args.game('ksp'), Game)

    def test_ckanmeta_remote_ksp2(self):
        path = f'{self.tmpdir.name}/upstream/ckan'
        self.assertEqual(
            Game('ksp2', self.shared_args).ckanmeta_remote, path)

    def test_netkan_remote_ksp2(self):
        path = f'{self.tmpdir.name}/upstream/netkan'
        self.assertEqual(
            Game('ksp2', self.shared_args).netkan_remote, path)
