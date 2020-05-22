import unittest
from time import time
from os import utime
from pathlib import Path, PurePath
from shutil import copy2
from tempfile import TemporaryDirectory
from click.testing import CliRunner
from git import Repo

from netkan.cli import clean_cache
from netkan.repos import NetkanRepo


# This file is intended to test the commands in cli.py, running them directly via click.testing.CliRunner().invoke().
class TestCleanCache(unittest.TestCase):

    cache_path = TemporaryDirectory()
    testdata_path = Path(PurePath(__file__).parent, 'testdata/NetKAN/')
    repo = NetkanRepo(Repo.init(testdata_path))

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

        result = self.runner.invoke(clean_cache, ['--days', '42', '--cache', self.cache_path.name])

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(Path.exists(self.target_file_1))
        self.assertTrue(Path.exists(self.target_file_2))
