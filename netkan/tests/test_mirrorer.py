import unittest

from netkan.mirrorer import CkanMirror


# I don't know how to test Mirrorer, it needs a queue and archive.org access


class TestCkanMirrorRedistributable(unittest.TestCase):

    def setUp(self):
        self.ckan_mirror = CkanMirror("kspckanmods", contents="""{
            "spec_version": "v1.4",
            "identifier":   "AwesomeMod",
            "name":         "Awesome Mod",
            "abstract":     "A great mod",
            "version":      "1.0.0",
            "ksp_version":  "1.7.3",
            "author":       [ "techman83", "DasSkelett", "politas" ],
            "license":      [ "CC-BY-NC-SA-4.0", "GPL-3.0", "MIT" ],
            "download_content_type": "application/zip",
            "download_size": 33333,
            "download_hash": {
                "sha1": "DF564E21929EA07C624F822E5C43B7D0A3B0DBDF"
            }
        }""")

    def test_can_mirror(self):
        self.assertTrue(self.ckan_mirror.redistributable)
        self.assertTrue(self.ckan_mirror.can_mirror)

    def test_license_urls(self):
        self.assertEqual(self.ckan_mirror.license_urls(), [
            'http://creativecommons.org/licenses/by-nc-sa/4.0',
            'http://www.gnu.org/licenses/gpl-3.0.en.html',
            'https://opensource.org/licenses/MIT',
        ])

    def test_strings(self):
        self.assertEqual(self.ckan_mirror.mirror_item(), "AwesomeMod-1.0.0")
        self.assertEqual(self.ckan_mirror.mirror_filename(), "DF564E21-AwesomeMod-1.0.0.zip")
        self.assertEqual(self.ckan_mirror.mirror_title(), "Awesome Mod - 1.0.0")
        self.assertEqual(self.ckan_mirror.mirror_description,
                         "A great mod<br><br>License(s): CC-BY-NC-SA-4.0 GPL-3.0 MIT")
        self.assertEqual(self.ckan_mirror.mirror_source_filename(),
                         "AwesomeMod-1.0.0.source.zip")

    def test_ia_data(self):
        self.assertEqual(self.ckan_mirror.item_metadata,
                         {
                             'title':       "Awesome Mod - 1.0.0",
                             'description':
                                 "A great mod<br><br>License(s): CC-BY-NC-SA-4.0 GPL-3.0 MIT",
                             'creator':     ["techman83", "DasSkelett", "politas"],
                             'collection':  "kspckanmods",
                             'subject':     'ksp; kerbal space program; mod',
                             'mediatype':   'software',
                             'licenseurl':  [
                                 'http://creativecommons.org/licenses/by-nc-sa/4.0',
                                 'http://www.gnu.org/licenses/gpl-3.0.en.html',
                                 'https://opensource.org/licenses/MIT',
                             ],
                         })
        self.assertEqual(self.ckan_mirror.download_headers,
                         {
                             'Content-Type':           "application/zip",
                             'Content-Length':         "33333",
                             'x-amz-auto-make-bucket': "1",
                         })


class TestCkanMirrorRestricted(unittest.TestCase):

    def setUp(self):
        self.ckan_mirror = CkanMirror("kspckanmods", contents="""{
            "spec_version": "v1.4",
            "identifier":   "AwesomeMod",
            "version":      "1.0.0",
            "ksp_version":  "1.7.3",
            "author":       [ "techman83", "DasSkelett", "politas" ],
            "license":      "restricted",
            "download_content_type": "application/zip"
        }""")

    def test_can_mirror(self):
        self.assertFalse(self.ckan_mirror.redistributable)
        self.assertFalse(self.ckan_mirror.can_mirror)


class TestCkanMirrorGitHub(unittest.TestCase):

    def setUp(self):
        self.ckan_mirror = CkanMirror("kspckanmods", contents="""{
            "spec_version": "v1.4",
            "resources": {
                "repository": "https://github.com/HebaruSan/Astrogator/releases"
            }
        }""")

    def test_source_download(self):
        self.assertEqual(self.ckan_mirror.source_download(),
                         "https://github.com/HebaruSan/Astrogator/archive/master.zip")

    def test_source_download_alt_branch(self):
        self.assertEqual(self.ckan_mirror.source_download('primary'),
                         "https://github.com/HebaruSan/Astrogator/archive/primary.zip")


class TestCkanMirrorGitLab(unittest.TestCase):

    def setUp(self):
        self.ckan_mirror = CkanMirror("kspckanmods", contents="""{
            "spec_version": "v1.4",
            "resources": {
                "repository": "https://gitlab.com/N70/Kerbalism/"
            }
        }""")

    def test_source_download(self):
        self.assertEqual(self.ckan_mirror.source_download(),
                         "https://gitlab.com/N70/Kerbalism/-/archive/master/Kerbalism-master.zip")


class TestCkanMirrorButBucket(unittest.TestCase):

    def setUp(self):
        self.ckan_mirror = CkanMirror("kspckanmods", contents="""{
            "spec_version": "v1.4",
            "resources": {
                "repository": "https://bitbucket.org/blowfishpro/b9-aerospace/src"
            }
        }""")

    def test_source_download(self):
        self.assertEqual(self.ckan_mirror.source_download(),
                         "https://bitbucket.org/blowfishpro/b9-aerospace/get/master.zip")
