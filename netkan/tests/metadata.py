from netkan.metadata import Netkan, Ckan

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

    def test_kref_id(self):
        self.assertEqual(self.netkan.kref_id, 'pjf/DogeCoinFlag')

    def test_hook_only(self):
        self.assertFalse(self.netkan.hook_only())


class TestNetKANSpaceDock(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(Path(self.test_data, 'NetKAN/DockCoinFlag.netkan'))

    def test_has_spacedock_kref(self):
        self.assertEqual(self.netkan.kref, '#/ckan/spacedock/777')

    def test_on_spacedock(self):
        self.assertTrue(self.netkan.on_spacedock)

    def test_kref_id(self):
        self.assertEqual(self.netkan.kref_id, '777')

    def test_hook_only(self):
        self.assertTrue(self.netkan.hook_only())


class TestNetKANCurse(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(Path(self.test_data, 'NetKAN/CurseCoinFlag.netkan'))

    def test_has_curse_kref(self):
        self.assertEqual(self.netkan.kref, '#/ckan/curse/666')

    def test_on_curse(self):
        self.assertTrue(self.netkan.on_curse)

    def test_kref_id(self):
        self.assertEqual(self.netkan.kref_id, '666')

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

    def test_kref_id(self):
        self.assertEqual(
            self.netkan.kref_id,
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


class TestCkanSimple(unittest.TestCase):

    def setUp(self):
        self.ckan = Ckan(contents = """{
            "spec_version": "v1.4",
            "identifier":   "AwesomeMod",
            "version":      "1.0.0",
            "ksp_version":  "1.7.3",
            "author":       "techman83",
            "license":      "CC-BY-NC-SA-4.0",
            "download":     "https://awesomesite.org/awesomemod-1.0.0.zip",
            "download_content_type": "application/zip"
        }""")

    def test_basic_properties(self):
        self.assertEqual(self.ckan.spec_version, "v1.4")
        self.assertEqual(self.ckan.identifier,   "AwesomeMod")
        self.assertEqual(self.ckan.version,      "1.0.0")
        self.assertEqual(self.ckan.ksp_version,  "1.7.3")

    def test_default_kind(self):
        self.assertEqual(self.ckan.kind, "package")

    def test_authors(self):
        self.assertEqual(self.ckan.authors(), ["techman83"])

    def test_licenses(self):
        self.assertEqual(self.ckan.licenses(), ["CC-BY-NC-SA-4.0"])

    def test_cache(self):
        self.assertEqual(self.ckan.cache_prefix,   "3C69B375")
        self.assertEqual(self.ckan.cache_filename, "3C69B375-AwesomeMod-1.0.0.zip")


class TestCkanComplex(unittest.TestCase):

    def setUp(self):
        self.ckan = Ckan(contents = """{
            "spec_version": "v1.4",
            "identifier":   "AwesomeMod",
            "version":      "1.0.0",
            "ksp_version":  "1.7.3",
            "author":       [ "techman83", "DasSkelett", "politas" ],
            "license":      [ "CC-BY-NC-SA-4.0", "GPL-3.0", "MIT" ],
            "kind":         "metapackage"
        }""")

    def test_explicit_kind(self):
        self.assertEqual(self.ckan.kind, "metapackage")

    def test_authors(self):
        self.assertEqual(self.ckan.authors(), ["techman83", "DasSkelett", "politas"])

    def test_licenses(self):
        self.assertEqual(self.ckan.licenses(), ["CC-BY-NC-SA-4.0", "GPL-3.0", "MIT"])
