import unittest
from pathlib import Path, PurePath
from git import Repo

from netkan.download_counter import NetkanDownloads
from netkan.repos import NetkanRepo


class TestNetKANCounter(unittest.TestCase):
    repo = NetkanRepo(Repo.init(Path(PurePath(__file__).parent, 'testdata/NetKAN')))


class TestNetKANGitHubCounts(TestNetKANCounter):

    def setUp(self):
        self.netkan = NetkanDownloads(self.repo.nk_path('DogeCoinFlag'), 'token')

    def test_github_repo_api(self):
        self.assertEqual(
            self.netkan.github_repo_api,
            'https://api.github.com/repos/pjf/DogeCoinFlag'
        )


class TestNetKANSpaceDockCounts(TestNetKANCounter):

    def setUp(self):
        self.netkan = NetkanDownloads(self.repo.nk_path('DockCoinFlag'), 'token')

    def test_spacedock_api(self):
        self.assertEqual(
            self.netkan.spacedock_api,
            'https://spacedock.info/api/mod/777'
        )


class TestNetKANCurseCounts(TestNetKANCounter):

    def setUp(self):
        self.netkan = NetkanDownloads(self.repo.nk_path('CurseCoinFlag'), 'token')

    def test_curse_api_numeric(self):
        self.assertEqual(
            self.netkan.curse_api,
            'https://api.cfwidget.com/project/666'
        )

    def test_curse_api(self):
        self.netkan.kref_id = 'a666'
        self.assertEqual(
            self.netkan.curse_api,
            'https://api.cfwidget.com/kerbal/ksp-mods/a666'
        )


class TestNetKANNetkanCounts(TestNetKANCounter):

    def setUp(self):
        self.netkan = NetkanDownloads(self.repo.nk_path('NetkanCoinFlag'), 'token')

    def test_remote_netkan(self):
        self.assertEqual(
            self.netkan.kref_id,
            'http://ksp-ckan.space/netkan/DogeCoinFlag.netkan'
        )


class TestNetKANUnknownCounts(TestNetKANCounter):

    def setUp(self):
        self.netkan = NetkanDownloads(self.repo.nk_path('UnknownCoinFlag'), 'token')

    def test_github_repo_api(self):
        self.assertEqual(self.netkan.get_count(), 0)
