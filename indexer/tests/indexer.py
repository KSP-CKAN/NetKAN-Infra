from netkan_indexer.indexer import CkanMessage

import unittest
import tempfile
import shutil
from unittest import mock
from pathlib import Path, PurePath
from git import Repo
from datetime import datetime

class TestCkan(unittest.TestCase):
    test_data = Path(PurePath(__file__).parent, 'testdata/no_change')

    @classmethod
    def setUpClass(cls):
        super(TestCkan, cls).setUpClass()
        cls.msg = mock.Mock()
        cls.msg.body = '{\n    "spec_version": 1,\n    "comment": "flagmod",\n    "identifier": "DogeCoinFlag",\n    "name": "Dogecoin Flag",\n    "abstract": "Such flag. Very currency. Wow.",\n    "description": "Adorn your craft with your favourite cryptocurrency. To the mün!",\n    "author": "daviddwk",\n    "license": "CC-BY",\n    "resources": {\n        "homepage": "https://www.reddit.com/r/dogecoin/comments/1tdlgg/i_made_a_more_accurate_dogecoin_and_a_ksp_flag/",\n        "repository": "https://github.com/pjf/DogeCoinFlag"\n    },\n    "version": "v1.02",\n    "ksp_version": "any",\n    "download": "https://github.com/pjf/DogeCoinFlag/releases/download/v1.02/DogeCoinFlag-1.02.zip",\n    "download_size": 53359,\n    "download_hash": {\n        "sha1": "BFB78381B5565E1AC7E9B2EB9C65B76EF7F6DF71",\n        "sha256": "CF70CE1F988F908FB9CF641C1E47CDA2A30D5AD951A4811A5C0C5D30F6FD3BA9"\n    },\n    "download_content_type": "application/zip",\n    "x_generated_by": "netkan"\n}\n'
        cls.msg.message_attributes = {
            'CheckTime': {'StringValue': '2019-06-24T19:06:14', 'DataType': 'String'},
            'ModIdentifier': {'StringValue': 'DogeCoinFlag', 'DataType': 'String'},
            'Staged': {'StringValue': 'False', 'DataType': 'String'},
            'Success': {'StringValue': 'True', 'DataType': 'String'},
            'FileName': {'StringValue': './DogeCoinFlag-v1.02.ckan', 'DataType': 'String'}
        }
        cls.msg.message_id = 'MessageMcMessageFace'
        cls.msg.receipt_handle = 'HandleMcHandleFace'
        cls.msg.md5_of_body = '709d9d3484f8c1c719b15a8c3425276a'
        cls.tmpdir = tempfile.TemporaryDirectory()
        working = Path(cls.tmpdir.name, 'working')
        upstream = Path(cls.tmpdir.name, 'upstream')
        upstream.mkdir()
        Repo.init(upstream, bare=True)
        shutil.copytree(cls.test_data, working)
        cls.ckan_meta = Repo.init(working)
        cls.ckan_meta.index.add(cls.ckan_meta.untracked_files)
        cls.ckan_meta.index.commit('Test Data')
        cls.ckan_meta.create_remote('origin', upstream.as_posix())
        cls.ckan_meta.remotes.origin.push('master:master')
        cls.message = CkanMessage(cls.msg, cls.ckan_meta)

    @classmethod
    def tearDownClass(cls):
        super(TestCkan, cls).tearDownClass()
        cls.tmpdir.cleanup()

    def tearDown(self):
        meta = self.message.ckan_meta
        meta.git.clean('-df')
        try:
            cleanup = meta.create_head('cleanup', 'HEAD~1')
            meta.head.reference = cleanup
            meta.head.reset(index=True, working_tree=True)
        except:
            pass

    def test_ckan_message_changed(self):
        self.assertFalse(self.message.metadata_changed())

    def test_ckan_message_mod_version(self):
        self.assertEqual('DogeCoinFlag-v1.02', self.message.mod_version)

    def test_ckan_message_success(self):
        self.assertTrue(self.message.Success)

    def test_ckan_message_identifier(self):
        self.assertEqual('DogeCoinFlag', self.message.ModIdentifier)

    def test_ckan_message_filename(self):
        self.assertEqual('DogeCoinFlag-v1.02.ckan', self.message.FileName)

    def test_ckan_message_stage(self):
        self.assertFalse(self.message.Staged)

    def test_ckan_message_delete_attrs(self):
        self.assertEqual(self.message.delete_attrs['Id'], 'MessageMcMessageFace')
        self.assertEqual(self.message.delete_attrs['ReceiptHandle'], 'HandleMcHandleFace')

    def test_ckan_message_repo_untracked(self):
        self.message.write_metadata()
        self.assertEqual(0, len(self.message.ckan_meta.untracked_files))

    def test_ckan_message_repo_dirty(self):
        self.message.write_metadata()
        self.assertFalse(self.message.ckan_meta.is_dirty())

    def test_ckan_message_write_md5_matches(self):
        self.message.write_metadata()
        self.assertEqual(self.message.md5_of_body, self.message.mod_file_md5())

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs()
        self.assertEqual(attrs.ModIdentifier, 'DogeCoinFlag')
        self.assertTrue(attrs.success)
        self.assertIsInstance(attrs.last_inflated, datetime)
        self.assertEqual(attrs.last_error, '')
        with self.assertRaises(AttributeError):
            attrs.last_indexed


class TestUpdateCkan(TestCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/changed')

    def test_ckan_message_changed(self):
        self.assertTrue(self.message.metadata_changed())

    def test_ckan_message_repo_dirty(self):
        self.message.write_metadata()
        self.assertTrue(self.message.ckan_meta.is_dirty())

    def test_ckan_message_commit(self):
        self.message.write_metadata()
        c = self.message.commit_metadata()
        self.assertEqual(0, len(self.message.ckan_meta.untracked_files))
        self.assertEqual(c.message, 'NetKAN generated mods - DogeCoinFlag-v1.02')

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs()
        self.assertEqual(attrs.ModIdentifier, 'DogeCoinFlag')
        self.assertTrue(attrs.success)
        self.assertIsInstance(attrs.last_inflated, datetime)
        self.assertIsInstance(attrs.last_indexed, datetime)


class TestStagedCkan(TestUpdateCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/changed')

    def setUp(self):
        super().setUp()
        self.msg.message_attributes['Staged'] = {'StringValue': 'True', 'DataType': 'String'}
        self.message = CkanMessage(self.msg, self.ckan_meta)

    def test_ckan_message_changed(self):
        with self.message.change_branch():
            self.assertTrue(self.message.metadata_changed())

    def test_ckan_message_commit(self):
        with self.message.change_branch():
            self.message.write_metadata()
            c = self.message.commit_metadata()
            self.assertEqual(0, len(self.message.ckan_meta.untracked_files))
            self.assertEqual(c.message, 'NetKAN generated mods - DogeCoinFlag-v1.02')
        self.assertEqual(
            self.message.ckan_meta.head.commit.message,
            'Test Data'
        )

    def test_ckan_message_stage(self):
        self.assertTrue(self.message.Staged)

    def test_ckan_message_change_branch(self):
        self.assertEqual(str(self.message.ckan_meta.active_branch), 'master')
        with self.message.change_branch():
            self.assertEqual(str(self.message.ckan_meta.active_branch), 'DogeCoinFlag-v1.02')
        self.assertEqual(str(self.message.ckan_meta.active_branch), 'master')

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs()
        self.assertEqual(attrs.ModIdentifier, 'DogeCoinFlag')
        self.assertTrue(attrs.success)
        self.assertIsInstance(attrs.last_inflated, datetime)
        with self.assertRaises(AttributeError):
            attrs.last_indexed


class TestNewCkan(TestUpdateCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/empty')

    def test_ckan_message_repo_untracked(self):
        self.message.write_metadata()
        self.assertEqual(1, len(self.message.ckan_meta.untracked_files))

    def test_ckan_message_repo_dirty(self):
        self.message.write_metadata()
        self.assertFalse(self.message.ckan_meta.is_dirty())


class TestFailedCkan(TestCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/no_change')

    def setUp(self):
        super().setUp()
        self.msg.message_attributes['Success'] = {'StringValue': 'False', 'DataType': 'String'}
        self.msg.message_attributes['ErrorMessage'] = {
            'StringValue': 'Curl download failed with error CouldntConnect',
            'DataType': 'String'
        }
        self.message = CkanMessage(self.msg, self.ckan_meta)

    def test_ckan_message_success(self):
        self.assertFalse(self.message.Success)

    def test_ckan_message_error_message(self):
        self.assertEqual(self.message.ErrorMessage, 'Curl download failed with error CouldntConnect')

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs()
        self.assertEqual(attrs.ModIdentifier, 'DogeCoinFlag')
        self.assertFalse(attrs.success)
        self.assertIsInstance(attrs.last_inflated, datetime)
        self.assertEqual(attrs.last_error, 'Curl download failed with error CouldntConnect')
        with self.assertRaises(AttributeError):
            attrs.last_indexed

