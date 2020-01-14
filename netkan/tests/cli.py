from netkan.cli import clean_cache

import unittest
from time import time
from os import utime
from pathlib import Path, PurePath
from shutil import copy2
from click.testing import CliRunner


# This file is intended to test the commands in cli.py, running them directly via click.testing.CliRunner().invoke().
class TestCleanCache(unittest.TestCase):

    cache_path = Path(PurePath(__file__).parent, 'test_cache')
    testdata_path = Path(PurePath(__file__).parent, 'testdata/NetKAN/NetKAN/')

    cache_path.mkdir(exist_ok=True)

    source_file_1 = Path(testdata_path, 'DogeCoinFlag.netkan')
    source_file_2 = Path(testdata_path, 'FlagCoinDoge.netkan')
    # Pretend they are zip files.
    target_file_1 = Path(cache_path, 'DogeCoinFlag.zip')
    target_file_2 = Path(cache_path, 'FlagCoinDoge.zip')

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

        if self.target_file_1.exists():
            self.target_file_1.unlink()
        if self.target_file_2.exists():
            self.target_file_2.unlink()

    def test_clean_all(self):

        result = self.runner.invoke(clean_cache, ['--days', '42', '--cache', str(self.cache_path)])

        self.assertEqual(result.exit_code, 0)
        self.assertFalse(Path.exists(self.target_file_1))
        self.assertTrue(Path.exists(self.target_file_2))
