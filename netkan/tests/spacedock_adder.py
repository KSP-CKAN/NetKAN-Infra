# pylint: disable-all
# flake8: noqa

from unittest import mock

from netkan.spacedock_adder import (
    SpaceDockMessageHandler, SpaceDockAdderQueueHandler
)
from netkan.repos import NetkanRepo

from .common import SharedArgsHarness


class TestSpaceDockMessageHandler(SharedArgsHarness):

    def setUp(self):
        super().setUp()
        self.handler = SpaceDockMessageHandler(
            game=self.shared_args.game('ksp'))

    def test_class_string(self):
        self.handler.append(self.mocked_message())
        self.assertEqual(str(
            self.handler), 'Dogecoin Flag')

    def test_add_primary(self):
        self.handler.append(self.mocked_message(
            filename='DogeCoinFlag.netkan'))
        self.assertEqual(len(self.handler), 1)
        self.assertEqual(
            self.handler.queued[0].info.get('name'),
            'Dogecoin Flag'
        )

    def test_branch_checkout_primary_on_enter(self):
        repo = self.shared_args.game('ksp').netkan_repo
        with repo.change_branch('test_branch'):
            self.assertTrue(repo.is_active_branch('test_branch'))
        repo.checkout_branch('test_branch')
        self.assertTrue(repo.is_active_branch('test_branch'))
        with SpaceDockMessageHandler(game=self.shared_args.game('ksp')) as handler:
            self.assertIsInstance(repo, NetkanRepo)
            self.assertTrue(repo.is_active_branch('master'))

    @mock.patch('netkan.spacedock_adder.SpaceDockAdder.try_add')
    def test_process_netkans(self, mocked_process):
        mocked_process.return_value = True
        self.handler.append(self.mocked_message())
        self.handler.process_messages()
        self.assertEqual(len(self.handler.processed), 1)

    @mock.patch('netkan.spacedock_adder.SpaceDockAdder.try_add')
    def test_process_netkans_fail(self, mocked_process):
        mocked_process.return_value = False
        self.handler.append(self.mocked_message())
        self.assertEqual(len(self.handler.queued), 1)
        self.handler.process_messages()
        self.assertEqual(len(self.handler.processed), 0)

    @mock.patch('netkan.spacedock_adder.SpaceDockAdder.try_add')
    def test_delete_attrs(self, mocked_process):
        mocked_process.return_value = True
        self.handler.append(self.mocked_message())
        self.handler.process_messages()
        attrs = [{'Id': 'MessageMcMessageFace',
                  'ReceiptHandle': 'HandleMcHandleFace'}]
        self.assertEqual(self.handler.sqs_delete_entries(), attrs)
        self.assertEqual(len(self.handler.processed), 0)


class TestSpaceDockAdderQueueHandler(SharedArgsHarness):

    def test_ksp_message_append(self):
        adder = SpaceDockAdderQueueHandler(self.shared_args)
        adder.append_message('ksp', self.mocked_message())
        self.assertTrue('ksp' in adder.game_handlers)

    def test_ksp_message_no_ksp2(self):
        adder = SpaceDockAdderQueueHandler(self.shared_args)
        adder.append_message('ksp', self.mocked_message())
        self.assertFalse('ksp2' in adder.game_handlers)

    def test_ksp2_message_append(self):
        adder = SpaceDockAdderQueueHandler(self.shared_args)
        adder.append_message('ksp2', self.mocked_message())
        self.assertTrue('ksp2' in adder.game_handlers)
