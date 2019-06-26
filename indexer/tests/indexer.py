from netkan_indexer.indexer import CkanMessage

import unittest
from unittest import mock
from pathlib import Path, PurePath

class TestCkanMessage(unittest.TestCase):

    def setUp(self):
        self.msg = mock.Mock()
        self.msg.body = '{\n    "spec_version": 1,\n    "comment": "flagmod",\n    "identifier": "DogeCoinFlag",\n    "name": "Dogecoin Flag",\n    "abstract": "Such flag. Very currency. Wow.",\n    "description": "Adorn your craft with your favourite cryptocurrency. To the mün!",\n    "author": "daviddwk",\n    "license": "CC-BY",\n    "resources": {\n        "homepage": "https://www.reddit.com/r/dogecoin/comments/1tdlgg/i_made_a_more_accurate_dogecoin_and_a_ksp_flag/",\n        "repository": "https://github.com/pjf/DogeCoinFlag"\n    },\n    "version": "v1.02",\n    "ksp_version": "any",\n    "download": "https://github.com/pjf/DogeCoinFlag/releases/download/v1.02/DogeCoinFlag-1.02.zip",\n    "download_size": 53359,\n    "download_hash": {\n        "sha1": "BFB78381B5565E1AC7E9B2EB9C65B76EF7F6DF71",\n        "sha256": "CF70CE1F988F908FB9CF641C1E47CDA2A30D5AD951A4811A5C0C5D30F6FD3BA9"\n    },\n    "download_content_type": "application/zip",\n    "x_generated_by": "netkan"\n}\n'
        self.msg.message_attributes = {
            'CheckTime': {'StringValue': '2019-06-24T19:06:14', 'DataType': 'String'},
            'ModIdentifier': {'StringValue': 'DogeCoinFlag', 'DataType': 'String'},
            'Staged': {'StringValue': 'False', 'DataType': 'String'},
            'Success': {'StringValue': 'True', 'DataType': 'String'},
            'FileName': {'StringValue': './DogeCoinFlag-v1.02.ckan', 'DataType': 'String'}
        }
        self.msg.message_id = 'MessageMcMessageFace'
        self.msg.receipt_handle = 'HandleMcHandleFace'
        self.msg.md5_of_body = '709d9d3484f8c1c719b15a8c3425276a'
        self.meta_path = Path(PurePath(__file__).parent, 'testdata')

    def test_ckan_message_success(self):
        message = CkanMessage(self.msg, self.meta_path)
        self.assertTrue(message.Success)

    def test_ckan_message_identifier(self):
        message = CkanMessage(self.msg, self.meta_path)
        self.assertEqual('DogeCoinFlag', message.ModIdentifier)

    def test_ckan_message_filename(self):
        message = CkanMessage(self.msg, self.meta_path)
        self.assertEqual('DogeCoinFlag-v1.02.ckan', message.FileName)

    def test_ckan_message_stage(self):
        message = CkanMessage(self.msg, self.meta_path)
        self.assertFalse(message.Staged)

    def test_ckan_message_md5(self):
        message = CkanMessage(self.msg, self.meta_path)
        self.assertTrue(message.metadata_changed())

    def test_ckan_message_delete_attrs(self):
        message = CkanMessage(self.msg, self.meta_path)

        self.assertEqual(message.delete_attrs['Id'], 'MessageMcMessageFace')
        self.assertEqual(message.delete_attrs['ReceiptHandle'], 'HandleMcHandleFace')

