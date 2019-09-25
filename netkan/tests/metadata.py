from netkan.metadata import Netkan

import unittest
from pathlib import Path, PurePath


class TestNetKAN(unittest.TestCase):
    test_data = Path(PurePath(__file__).parent, 'testdata/NetKAN')


class TestNetKANGitHub(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(Path(self.test_data, 'NetKAN/DogeCoinFlag.netkan'))

    def test_has_github_kref(self):
        self.assertEqual(self.netkan.kref, '#/ckan/github/pjf/DogeCoinFlag')

    def test_on_github(self):
        self.assertTrue(self.netkan.on_github)

    def test_mod_id(self):
        self.assertEqual(self.netkan.mod_id, 'pjf/DogeCoinFlag')

    def test_hook_only(self):
        self.assertFalse(self.netkan.hook_only())


class TestNetKANSpaceDock(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(Path(self.test_data, 'NetKAN/DockCoinFlag.netkan'))

    def test_has_spacedock_kref(self):
        self.assertEqual(self.netkan.kref, '#/ckan/spacedock/777')

    def test_on_spacedock(self):
        self.assertTrue(self.netkan.on_spacedock)

    def test_mod_id(self):
        self.assertEqual(self.netkan.mod_id, '777')

    def test_hook_only(self):
        self.assertTrue(self.netkan.hook_only())


class TestNetKANCurse(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(Path(self.test_data, 'NetKAN/CurseCoinFlag.netkan'))

    def test_has_curse_kref(self):
        self.assertEqual(self.netkan.kref, '#/ckan/curse/666')

    def test_on_curse(self):
        self.assertTrue(self.netkan.on_curse)

    def test_mod_id(self):
        self.assertEqual(self.netkan.mod_id, '666')

    def test_hook_only(self):
        self.assertFalse(self.netkan.hook_only())


class TestNetKANNetkan(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(Path(self.test_data, 'NetKAN/NetkanCoinFlag.netkan'))

    def test_has_netkan_kref(self):
        self.assertEqual(
            self.netkan.kref,
            '#/ckan/netkan/http://ksp-ckan.space/netkan/DogeCoinFlag.netkan'
        )

    def test_on_netkan(self):
        self.assertTrue(self.netkan.on_netkan)

    def test_mod_id(self):
        self.assertEqual(
            self.netkan.mod_id,
            'http://ksp-ckan.space/netkan/DogeCoinFlag.netkan'
        )

    def test_hook_only(self):
        self.assertFalse(self.netkan.hook_only())


class TestNetKANVref(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(Path(self.test_data, 'NetKAN/VrefCoinFlag.netkan'))

    def test_on_spacedock(self):
        self.assertTrue(self.netkan.on_spacedock)

    def test_hook_only(self):
        self.assertFalse(self.netkan.hook_only())
