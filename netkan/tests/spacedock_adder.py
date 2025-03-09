# pylint: disable-all
# flake8: noqa

from unittest import mock

from netkan.spacedock_adder import (
    SpaceDockAdder,
    SpaceDockMessageHandler,
    SpaceDockAdderQueueHandler
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
            self.assertTrue(repo.is_active_branch('main'))

    @mock.patch('netkan.spacedock_adder.SpaceDockAdder.try_add')
    def test_process_netkans(self, mocked_process):
        mocked_process.return_value = True
        self.handler.append(self.mocked_message())
        processed = self.handler.process_messages()
        self.assertEqual(len(processed), 1)

    @mock.patch('netkan.spacedock_adder.SpaceDockAdder.try_add')
    def test_process_netkans_fail(self, mocked_process):
        mocked_process.return_value = False
        self.handler.append(self.mocked_message())
        self.assertEqual(len(self.handler.queued), 1)
        processed = self.handler.process_messages()
        self.assertEqual(len(processed), 0)

    @mock.patch('netkan.spacedock_adder.SpaceDockAdder.try_add')
    def test_delete_attrs(self, mocked_process):
        mocked_process.return_value = True
        self.handler.append(self.mocked_message())
        processed = self.handler.process_messages()
        attrs = [{'Id': 'MessageMcMessageFace',
                  'ReceiptHandle': 'HandleMcHandleFace'}]
        self.assertEqual(processed, attrs)


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


class TestSpaceDockAdder(SharedArgsHarness):

    def setUp(self):
        super().setUp()
        self.adder = SpaceDockAdder(
            self.mocked_message(filename='NotAnotherFlag.netkan'),
            nk_repo=self.shared_args.game('ksp').netkan_repo,
            game=self.shared_args.game('ksp'),
            github_pr=mock.MagicMock()
        )

    def test_netkan_already_exists(self):
        self.adder.nk_repo.nk_path('NotAnotherFlag').touch()
        self.adder.try_add()
        self.adder.nk_repo.nk_path('NotAnotherFlag').unlink()
        self.assertEqual(len(self.adder.github_pr.method_calls), 0)

    def test_frozen_already_exists(self):
        self.adder.nk_repo.frozen_path('NotAnotherFlag').touch()
        self.adder.try_add()
        self.adder.nk_repo.frozen_path('NotAnotherFlag').unlink()
        self.assertEqual(len(self.adder.github_pr.method_calls), 0)

    def test_netkan_creates_add_branch(self):
        self.adder.try_add()
        refs = [x.name for x in self.adder.nk_repo.git_repo.refs]
        self.assertTrue('add/NotAnotherFlag' in refs)

    def test_netkan_creates_pr(self):
        self.adder.try_add()
        refs = [x.name for x in self.adder.nk_repo.git_repo.refs]
        self.assertEqual(len(self.adder.github_pr.method_calls), 1)
