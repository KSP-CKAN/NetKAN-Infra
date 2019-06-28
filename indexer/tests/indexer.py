from netkan_indexer.indexer import CkanMessage

import unittest
import tempfile
import shutil
from unittest import mock
from pathlib import Path, PurePath
from git import Repo

class TestCkan(unittest.TestCase):
    test_data = Path(PurePath(__file__).parent, 'testdata/no_change')

    @classmethod
    def setUpClass(cls):
        super(TestCkan, cls).setUpClass()
        msg = mock.Mock()
        msg.body = '{\n    "spec_version": 1,\n    "comment": "flagmod",\n    "identifier": "DogeCoinFlag",\n    "name": "Dogecoin Flag",\n    "abstract": "Such flag. Very currency. Wow.",\n    "description": "Adorn your craft with your favourite cryptocurrency. To the mün!",\n    "author": "daviddwk",\n    "license": "CC-BY",\n    "resources": {\n        "homepage": "https://www.reddit.com/r/dogecoin/comments/1tdlgg/i_made_a_more_accurate_dogecoin_and_a_ksp_flag/",\n        "repository": "https://github.com/pjf/DogeCoinFlag"\n    },\n    "version": "v1.02",\n    "ksp_version": "any",\n    "download": "https://github.com/pjf/DogeCoinFlag/releases/download/v1.02/DogeCoinFlag-1.02.zip",\n    "download_size": 53359,\n    "download_hash": {\n        "sha1": "BFB78381B5565E1AC7E9B2EB9C65B76EF7F6DF71",\n        "sha256": "CF70CE1F988F908FB9CF641C1E47CDA2A30D5AD951A4811A5C0C5D30F6FD3BA9"\n    },\n    "download_content_type": "application/zip",\n    "x_generated_by": "netkan"\n}\n'
        msg.message_attributes = {
            'CheckTime': {'StringValue': '2019-06-24T19:06:14', 'DataType': 'String'},
            'ModIdentifier': {'StringValue': 'DogeCoinFlag', 'DataType': 'String'},
            'Staged': {'StringValue': 'False', 'DataType': 'String'},
            'Success': {'StringValue': 'True', 'DataType': 'String'},
            'FileName': {'StringValue': './DogeCoinFlag-v1.02.ckan', 'DataType': 'String'}
        }
        msg.message_id = 'MessageMcMessageFace'
        msg.receipt_handle = 'HandleMcHandleFace'
        msg.md5_of_body = '709d9d3484f8c1c719b15a8c3425276a'
        cls.tmpdir = tempfile.TemporaryDirectory()
        working = Path(cls.tmpdir.name, 'working')
        shutil.copytree(cls.test_data, working)
        ckan_meta = Repo.init(working)
        ckan_meta.index.add(ckan_meta.untracked_files)
        ckan_meta.index.commit('Test Data')
        cls.message = CkanMessage(msg, ckan_meta)

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

class TestNewCkan(TestUpdateCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/empty')

    def test_ckan_message_repo_untracked(self):
        self.message.write_metadata()
        self.assertEqual(1, len(self.message.ckan_meta.untracked_files))

    def test_ckan_message_repo_dirty(self):
        self.message.write_metadata()
        self.assertFalse(self.message.ckan_meta.is_dirty())

