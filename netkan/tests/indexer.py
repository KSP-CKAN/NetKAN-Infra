# pylint: disable-all
# flake8: noqa

import unittest
import tempfile
import shutil
from unittest import mock
from pathlib import Path, PurePath
from git import Repo
from datetime import datetime
from gitdb.exc import BadName

from netkan.indexer import CkanMessage, MessageHandler, IndexerQueueHandler
from netkan.repos import CkanMetaRepo

from .common import SharedArgsHarness


class TestCkan(unittest.TestCase):
    test_data = Path(PurePath(__file__).parent, 'testdata/no_change')

    @classmethod
    def setUpClass(cls):
        super(TestCkan, cls).setUpClass()
        cls.msg = mock.Mock()
        cls.msg.body = Path(
            PurePath(__file__).parent,
            'testdata/DogeCoinFlag-v1.02.ckan'
        ).read_text()
        cls.msg.message_attributes = {
            'CheckTime': {
                'StringValue': '2019-06-24T19:06:14', 'DataType': 'String'},
            'ModIdentifier': {
                'StringValue': 'DogeCoinFlag', 'DataType': 'String'},
            'GameId': {
                'StringValue': 'ksp', 'DataType': 'String'},
            'Staged': {'StringValue': 'False', 'DataType': 'String'},
            'Success': {'StringValue': 'True', 'DataType': 'String'},
            'FileName': {
                'StringValue': './DogeCoinFlag-v1.02.ckan',
                'DataType': 'String'
            }
        }
        cls.msg.message_id = 'MessageMcMessageFace'
        cls.msg.receipt_handle = 'HandleMcHandleFace'
        cls.msg.md5_of_body = '709d9d3484f8c1c719b15a8c3425276a'
        cls.tmpdir = tempfile.TemporaryDirectory()
        working = Path(cls.tmpdir.name, 'working')
        upstream = Path(cls.tmpdir.name, 'upstream')
        upstream.mkdir()
        Repo.init(upstream, bare=True, initial_branch='main')
        shutil.copytree(cls.test_data, working)
        cls.ckan_meta = Repo.init(working)
        Path(cls.ckan_meta.working_dir, '.git',
             'HEAD').write_text('ref: refs/heads/main')
        cls.ckan_meta.index.add(cls.ckan_meta.untracked_files)
        cls.ckan_meta.index.commit('Test Data')
        cls.ckan_meta.create_remote('origin', upstream.as_posix())
        cls.ckan_meta.remotes.origin.push('main:main')
        # When we clone at repo access, we use a git clone which
        # sets this automatically.
        cls.ckan_meta.git.remote('set-head', 'origin', '-a')
        cls.ckm_repo = CkanMetaRepo(cls.ckan_meta)
        cls.message = CkanMessage(cls.msg, cls.ckm_repo)

    @classmethod
    def tearDownClass(cls):
        super(TestCkan, cls).tearDownClass()
        cls.tmpdir.cleanup()

    def tearDown(self):
        meta = self.ckan_meta
        meta.git.clean('-df')
        try:
            cleanup = meta.create_head('cleanup', 'HEAD~1')
            meta.head.reference = cleanup
            meta.head.reset(index=True, working_tree=True)
        except BadName:
            pass

    def test_ckan_message_changed(self):
        self.assertFalse(self.message.metadata_changed())

    def test_ckan_message_str(self):
        self.assertEqual('DogeCoinFlag: 2019-06-24T19:06:14',
                         str(self.message))

    def test_ckan_message_mod_version(self):
        self.assertEqual('DogeCoinFlag-v1.02', self.message.mod_version)

    def test_ckan_message_game_id(self):
        self.assertEqual(self.message.GameId, 'ksp')

    def test_ckan_message_success(self):
        self.assertTrue(self.message.Success)

    def test_ckan_message_identifier(self):
        self.assertEqual('DogeCoinFlag', self.message.ModIdentifier)

    def test_ckan_message_filename(self):
        self.assertEqual('DogeCoinFlag-v1.02.ckan', self.message.FileName)

    def test_ckan_message_stage(self):
        self.assertFalse(self.message.Staged)

    def test_ckan_message_stage_name(self):
        self.assertEqual('add/DogeCoinFlag-v1.02',
                         self.message.staging_branch_name)

    def test_ckan_message_delete_attrs(self):
        self.assertEqual(
            self.message.delete_attrs['Id'], 'MessageMcMessageFace'
        )
        self.assertEqual(
            self.message.delete_attrs['ReceiptHandle'],
            'HandleMcHandleFace'
        )

    def test_ckan_message_repo_untracked(self):
        self.message.write_metadata()
        self.assertEqual(0, len(self.ckan_meta.untracked_files))

    def test_ckan_message_repo_dirty(self):
        self.message.write_metadata()
        self.assertFalse(self.ckan_meta.is_dirty())

    def test_ckan_message_write_md5_matches(self):
        self.message.write_metadata()
        self.assertEqual(self.message.md5_of_body, self.message.mod_file_md5())

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs(new=True)
        self.assertEqual(attrs['ModIdentifier'], 'DogeCoinFlag')
        self.assertEqual(attrs['game_id'], 'ksp')
        self.assertTrue(attrs['success'])
        self.assertIsInstance(attrs['last_inflated'], datetime)
        self.assertEqual(attrs['last_error'], None)
        with self.assertRaises(KeyError):
            attrs['last_indexed']


class TestUpdateCkan(TestCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/changed')

    def test_ckan_message_changed(self):
        self.assertTrue(self.message.metadata_changed())

    def test_ckan_message_repo_dirty(self):
        self.message.write_metadata()
        self.assertTrue(self.ckan_meta.is_dirty())

    def test_ckan_message_commit(self):
        self.message.write_metadata()
        c = self.message.commit_metadata(True)
        self.assertEqual(0, len(self.ckan_meta.untracked_files))
        self.assertEqual(
            c.message, 'NetKAN added mod - DogeCoinFlag-v1.02'
        )

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs(new=True)
        self.assertEqual(attrs['ModIdentifier'], 'DogeCoinFlag')
        self.assertTrue(attrs['success'])
        self.assertIsInstance(attrs['last_inflated'], datetime)
        self.assertIsInstance(attrs['last_indexed'], datetime)


class TestStagedCkan(TestUpdateCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/changed')

    def setUp(self):
        super().setUp()
        self.msg.message_attributes['Staged'] = {
            'StringValue': 'True', 'DataType': 'String'
        }
        self.message = CkanMessage(self.msg, self.ckm_repo)

    def test_ckan_message_changed(self):
        with self.message.ckm_repo.change_branch(self.message.mod_version):
            self.assertTrue(self.message.metadata_changed())

    def test_ckan_message_commit(self):
        with self.message.ckm_repo.change_branch(self.message.mod_version):
            self.message.write_metadata()
            c = self.message.commit_metadata(True)
            self.assertEqual(0, len(self.ckan_meta.untracked_files))
            self.assertEqual(
                c.message, 'NetKAN added mod - DogeCoinFlag-v1.02'
            )
        self.assertEqual(
            self.ckan_meta.head.commit.message,
            'Test Data'
        )

    def test_ckan_message_stage(self):
        self.assertTrue(self.message.Staged)

    def test_ckan_message_change_branch(self):
        self.assertEqual(str(self.ckan_meta.active_branch), 'main')
        with self.message.ckm_repo.change_branch(self.message.mod_version):
            self.assertEqual(
                str(self.ckan_meta.active_branch), 'DogeCoinFlag-v1.02'
            )
        self.assertEqual(str(self.ckan_meta.active_branch), 'main')

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs(new=True)
        self.assertEqual(attrs['ModIdentifier'], 'DogeCoinFlag')
        self.assertTrue(attrs['success'])
        self.assertIsInstance(attrs['last_inflated'], datetime)
        with self.assertRaises(KeyError):
            attrs['last_indexed']


class TestNewCkan(TestUpdateCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/empty')

    def test_ckan_message_repo_untracked(self):
        self.message.write_metadata()
        self.assertEqual(1, len(self.ckan_meta.untracked_files))

    def test_ckan_message_repo_dirty(self):
        self.message.write_metadata()
        self.assertFalse(self.ckan_meta.is_dirty())


class TestFailedCkan(TestCkan):
    test_data = Path(PurePath(__file__).parent, 'testdata/no_change')

    def setUp(self):
        super().setUp()
        self.msg.message_attributes['Success'] = {
            'StringValue': 'False', 'DataType': 'String'
        }
        self.msg.message_attributes['ErrorMessage'] = {
            'StringValue': 'Curl download failed with error CouldntConnect',
            'DataType': 'String'
        }
        self.message = CkanMessage(self.msg, self.ckm_repo)

    def test_ckan_message_success(self):
        self.assertFalse(self.message.Success)

    def test_ckan_message_error_message(self):
        self.assertEqual(
            self.message.ErrorMessage,
            'Curl download failed with error CouldntConnect'
        )

    def test_ckan_message_status_attrs(self):
        attrs = self.message.status_attrs(new=True)
        self.assertEqual(attrs['ModIdentifier'], 'DogeCoinFlag')
        self.assertFalse(attrs['success'])
        self.assertIsInstance(attrs['last_inflated'], datetime)
        self.assertEqual(
            attrs['last_error'],
            'Curl download failed with error CouldntConnect'
        )
        with self.assertRaises(KeyError):
            attrs['last_indexed']


class TestMessageHandler(SharedArgsHarness):

    def setUp(self):
        super().setUp()
        self.handler = MessageHandler(game=self.shared_args.game('ksp'))

    def test_class_string(self):
        self.handler.append(self.mocked_message())
        self.handler.append(self.mocked_message(staged=True))
        self.assertEqual(str(
            self.handler), 'DogeCoinFlag: 2019-06-24T19:06:14 DogeCoinFlag: 2019-06-24T19:06:14')

    def test_add_primary(self):
        self.handler.append(self.mocked_message())
        self.assertEqual(len(self.handler), 1)
        self.assertEqual(
            self.handler.primary[0].ckan.name,
            'Dogecoin Flag'
        )

    def test_add_staged(self):
        self.handler.append(self.mocked_message(staged=True))
        self.assertEqual(len(self.handler), 1)
        self.assertEqual(
            self.handler.staged[0].ckan.name,
            'Dogecoin Flag'
        )

    def test_add_both(self):
        self.handler.append(self.mocked_message())
        self.handler.append(self.mocked_message(staged=True))
        self.assertEqual(len(self.handler), 2)
        self.assertEqual(len(self.handler.primary), 1)
        self.assertEqual(len(self.handler.staged), 1)

    def test_branch_checkout_primary_on_enter(self):
        repo = self.shared_args.game('ksp').ckanmeta_repo
        with repo.change_branch('test_branch'):
            self.assertTrue(repo.is_active_branch('test_branch'))
        repo.checkout_branch('test_branch')
        self.assertTrue(repo.is_active_branch('test_branch'))
        with MessageHandler(game=self.shared_args.game('ksp')) as handler:
            self.assertTrue(repo.is_primary_active())

    @mock.patch('netkan.indexer.CkanMessage.process_ckan')
    def test_process_ckans(self, mocked_process):
        self.handler.append(self.mocked_message())
        self.handler.append(self.mocked_message(staged=True))
        processed = self.handler.process_messages()
        self.assertEqual(len(processed), 2)

    @mock.patch('netkan.indexer.CkanMessage.process_ckan')
    def test_delete_attrs(self, mocked_process):
        self.handler.append(self.mocked_message())
        self.handler.append(self.mocked_message(staged=True))
        processed = self.handler.process_messages()
        attrs = [{'Id': 'MessageMcMessageFace', 'ReceiptHandle': 'HandleMcHandleFace'}, {
            'Id': 'MessageMcMessageFace', 'ReceiptHandle': 'HandleMcHandleFace'}]
        self.assertEqual(processed, attrs)


class TestIndexerQueueHandler(SharedArgsHarness):

    def test_ksp_message_append(self):
        indexer = IndexerQueueHandler(self.shared_args)
        indexer.append_message('ksp', self.mocked_message())
        self.assertTrue('ksp' in indexer.game_handlers)

    def test_ksp_message_no_ksp2(self):
        indexer = IndexerQueueHandler(self.shared_args)
        indexer.append_message('ksp', self.mocked_message())
        self.assertFalse('ksp2' in indexer.game_handlers)

    def test_ksp2_message_append(self):
        indexer = IndexerQueueHandler(self.shared_args)
        indexer.append_message('ksp2', self.mocked_message())
        self.assertTrue('ksp2' in indexer.game_handlers)
