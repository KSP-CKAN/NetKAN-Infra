import unittest
from pathlib import Path, PurePath
from git import Repo

from netkan.metadata import Netkan, Ckan
from netkan.repos import NetkanRepo, CkanMetaRepo


class TestNetKAN(unittest.TestCase):
    nk_repo = NetkanRepo(Repo(Path(PurePath(__file__).parent, 'testdata/NetKAN')))

    def test_netkan_message(self):
        dogecoinflag = self.nk_repo.nk_path('DogeCoinFlag')
        netkan = Netkan(dogecoinflag)
        message = netkan.sqs_message()
        self.assertEqual(
            message['MessageBody'],
            dogecoinflag.read_text()
        )
        self.assertEqual(message['MessageGroupId'], '1')


class TestNetKANGitHub(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(self.nk_repo.nk_path('DogeCoinFlag'))

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
        self.netkan = Netkan(self.nk_repo.nk_path('DockCoinFlag'))

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
        self.netkan = Netkan(self.nk_repo.nk_path('CurseCoinFlag'))

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
        self.netkan = Netkan(self.nk_repo.nk_path('NetkanCoinFlag'))

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


class TestNetKANNoKref(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(contents="""{
            "spec_version": "v1.4",
            "identifier":   "LightsOut-Fwiffo",
            "license":      "MIT",
            "version":      "v0.1.5.1",
            "download":     "https://cdn.rawgit.com/rkagerer/KSP-Fwiffo-Repository/master/Mods/LightsOut-Fwiffo-v0.1.5.1.zip"
        }""")

    def test_kref(self):
        self.assertFalse(self.netkan.has_kref)

    def test_kref_src(self):
        self.assertEqual(self.netkan.kref_src, None)

    def test_kref_id(self):
        self.assertEqual(self.netkan.kref_id, None)


class TestNetKANVref(TestNetKAN):

    def setUp(self):
        self.netkan = Netkan(self.nk_repo.nk_path('VrefCoinFlag'))

    def test_on_spacedock(self):
        self.assertTrue(self.netkan.on_spacedock)

    def test_hook_only(self):
        self.assertFalse(self.netkan.hook_only())


class TestCkanSimple(unittest.TestCase):

    def setUp(self):
        self.ckan = Ckan(contents="""{
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
        self.assertEqual(self.ckan.version.string,      "1.0.0")
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


class TestCkanSpacesInDownload(unittest.TestCase):

    def setUp(self):
        self.ckan = Ckan(contents="""{
            "spec_version": "v1.4",
            "identifier":   "NASA-CountDown",
            "version":      "1.3.9.1",
            "ksp_version":  "1.8",
            "author":       "linuxgurugamer",
            "license":      "CC-BY-NC-SA",
            "download":     "https://spacedock.info/mod/1462/NASA%20CountDown%20Clock%20Updated/download/1.3.9.1",
            "download_content_type": "application/zip"
        }""")

    def test_cache(self):
        self.assertEqual(self.ckan.cache_prefix,   "25B8A610")
        self.assertEqual(self.ckan.cache_filename, "25B8A610-NASA-CountDown-1.3.9.1.zip")


class TestCkanComplex(unittest.TestCase):

    def setUp(self):
        self.ckan = Ckan(contents="""{
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

    def test_version(self):
        self.assertEqual('1.0.0', self.ckan.version.string)


class TestCkanEmpty(unittest.TestCase):

    def setUp(self):
        self.ckan = Ckan(contents='{}')

    def test_version_none(self):
        self.assertIsNone(self.ckan.version)

    def test_cache_prefix(self):
        self.assertIsNone(self.ckan.cache_prefix)

    def test_cache_filename(self):
        self.assertIsNone(self.ckan.cache_filename)


class TestVersionConstruction(unittest.TestCase):

    def test_str(self):
        string = '1.2.3'
        v1 = Ckan.Version(string)

        self.assertEqual(string, str(v1))
        self.assertEqual(string, v1.string)


class TestVersionComparison(unittest.TestCase):

    def test_alpha(self):
        v1 = Ckan.Version('apple')
        v2 = Ckan.Version('banana')

        self.assertLess(v1, v2)

    def test_basic(self):
        v0 = Ckan.Version('1.2.0')
        v1 = Ckan.Version('1.2.0')
        v2 = Ckan.Version('1.2.1')

        self.assertLess(v1, v2)
        self.assertGreater(v2, v1)
        self.assertEqual(v1, v0)

    def test_issue1076(self):
        v0 = Ckan.Version('1.01')
        v1 = Ckan.Version('1.1')

        self.assertEqual(v1, v0)

    def test_sortAllNumbersBeforeDot(self):
        v0 = Ckan.Version('1.0_beta')
        v1 = Ckan.Version('1.0.1_beta')

        self.assertLess(v0, v1)
        self.assertGreater(v1, v0)

    def test_dotSeparatorForExtraData(self):
        v0 = Ckan.Version('1.0')
        v1 = Ckan.Version('1.0.repackaged')
        v2 = Ckan.Version('1.0.1')

        self.assertLess(v0, v1)
        self.assertLess(v1, v2)
        self.assertGreater(v1, v0)
        self.assertGreater(v2, v1)

    def test_unevenVersioning(self):
        v0 = Ckan.Version('1.1.0.0')
        v1 = Ckan.Version('1.1.1')

        self.assertLess(v0, v1)
        self.assertGreater(v1, v0)

    def test_complex(self):
        v1 = Ckan.Version('v6a12')
        v2 = Ckan.Version('v6a5')

        self.assertLess(v2, v1)
        self.assertGreater(v1, v2)
        self.assertNotEqual(v1, v2)

    def test_Epoch(self):
        v1 = Ckan.Version('1.2.0')
        v2 = Ckan.Version('1:1.2.0')

        self.assertLess(v1, v2)

    def test_agExt(self):
        v1 = Ckan.Version('1.20')
        v2 = Ckan.Version('1.22a')

        self.assertGreater(v2, v1)

    def test_differentEpochs(self):
        v1 = Ckan.Version('1:1')
        v2 = Ckan.Version('2:1')

        self.assertNotEqual(v1, v2)

    def test_testSuite(self):
        v1 = Ckan.Version('1.0')
        v2 = Ckan.Version('2.0')

        self.assertTrue(v1 < v2)
