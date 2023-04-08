import os
import sys

from unittest import mock, TestCase
from unittest.mock import MagicMock

from netkan.webhooks import create_app

from .common import SharedArgsMixin


def inflation_queue(_, game: str) -> MagicMock:
    queue = MagicMock()
    queue.url = f'{game}.queue.url'
    return queue


class WebhooksHarness(TestCase, SharedArgsMixin):

    @classmethod
    def setUpClass(cls) -> None:
        super(WebhooksHarness, cls).setUpClass()
        cls.configure_repos()

    @classmethod
    def tearDownClass(cls) -> None:
        super(WebhooksHarness, cls).setUpClass()
        cls.cleanup()

    def setUp(self) -> None:
        netkan = getattr(self, "netkan_upstream")
        ckan = getattr(self, "ckan_upstream")
        env_patcher = mock.patch.dict(
            os.environ,
            {
                'LC_ALL': os.environ.get('LC_ALL', 'C.UTF-8'),
                'LANG': os.environ.get('LANG', 'C.UTF-8'),
                'NETKAN_REMOTES': f'ksp={netkan} ksp2={netkan}',
                'CKANMETA_REMOTES': f'ksp={ckan} ksp2={ckan}',
                'SSH_KEY': '12345'
            },
            clear=True,
        )
        env_patcher.start()
        sys_patch = mock.patch.object(sys, 'argv', ['group', 'command'])
        sys_patch.start()
        patch = mock.patch(
            'netkan.cli.common.Game.clone_base', self.tmpdir.name)
        patch.start()
        app = create_app()
        app.config.update({
            "TESTING": True,
        })
        self.ctx = app.app_context()
        self.ctx.push()
        self.client = app.test_client()

    def tearDown(self) -> None:
        super().tearDown()
        mock.patch.stopall()


class TestWebhookGitHubInflate(WebhooksHarness):

    def setUp(self) -> None:
        super().setUp()
        queue_url = mock.patch(
            'netkan.webhooks.config.WebhooksConfig.inflation_queue', inflation_queue)
        queue_url.start()

    @staticmethod
    def mock_netkan_hook() -> dict:
        return {
            'ref': 'refs/heads/main',
            'commits': [
                {
                    'id': 'fec27dc0350adc7dc8659cde980d1eca9ce30167',
                    'added': [],
                    'modified': [
                        "NetKAN/DogeCoinFlag.netkan"
                    ]
                }
            ]
        }

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp(self, queued: MagicMock, sig: MagicMock):
        sig.return_value = True
        response = self.client.post(
            '/gh/inflate/ksp', json=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp',
        )
        self.assertEqual(call[2].get('QueueUrl'), 'ksp.queue.url')

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp2(self, queued: MagicMock, sig: MagicMock):
        sig.return_value = True
        response = self.client.post(
            '/gh/inflate/ksp2', json=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp2',
        )
        self.assertEqual(call[2].get('QueueUrl'), 'ksp2.queue.url')

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp_wrong_branch(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(ref='refs/heads/not_primary')
        response = self.client.post(
            '/gh/inflate/ksp', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'Wrong branch'})

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp2_wrong_branch(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(ref='refs/heads/not_primary')
        response = self.client.post(
            '/gh/inflate/ksp2', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'Wrong branch'})

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp_no_commits(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(commits=[])
        response = self.client.post(
            '/gh/inflate/ksp', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'No commits received'})

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp2_no_commits(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(commits=[])
        response = self.client.post(
            '/gh/inflate/ksp2', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'No commits received'})

    @mock.patch('netkan.status.ModStatus.get')
    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_freeze_ksp(self, sig: MagicMock, status: MagicMock):
        # This does not test the status, rather that we return a 204
        # when there are mods to freeze.
        sig.return_value = True
        mocked_status = mock.MagicMock()
        mocked_status.frozen = False
        status.return_value = mocked_status
        data = self.mock_netkan_hook()
        data.get('commits', [{}])[0].update({
            'added': ['NetKAN/DogeCoinFlag.frozen'],
            'modified': []
        })
        response = self.client.post(
            '/gh/inflate/ksp', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 204)

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    @mock.patch('netkan.status.ModStatus.get')
    def test_freeze_ksp2(self, status: MagicMock, sig: MagicMock):
        # This does not test the status, rather that we return a 204
        # when there are mods to freeze.
        sig.return_value = True
        mocked_status = mock.MagicMock()
        mocked_status.frozen = False
        status.return_value = mocked_status
        data = self.mock_netkan_hook()
        data.get('commits', [{}])[0].update({
            'added': ['NetKAN/DogeCoinFlag.frozen'],
            'modified': []
        })
        response = self.client.post(
            '/gh/inflate/ksp2', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 204)


class TestWebhookGitHubMirror(WebhooksHarness):

    def setUp(self) -> None:
        super().setUp()
        queue = MagicMock()
        queue.url = 'some.queue.url'
        queue_url = mock.patch(
            'netkan.webhooks.config.WebhooksConfig.mirror_queue', queue)
        queue_url.start()

    @staticmethod
    def mock_netkan_hook() -> dict:
        return {
            'ref': 'refs/heads/main',
            'commits': [
                {
                    'id': 'fec27dc0350adc7dc8659cde980d1eca9ce30167',
                    'added': [],
                    'modified': [
                        "DogeCoinFlag/DogeCoinFlag-v1.0.2.ckan"
                    ]
                }
            ]
        }

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp(self, queued: MagicMock, sig: MagicMock):
        sig.return_value = True
        response = self.client.post(
            '/gh/mirror/ksp', json=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp',
        )

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp2(self, queued: MagicMock, sig: MagicMock):
        sig.return_value = True
        response = self.client.post(
            '/gh/mirror/ksp2', json=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp2',
        )

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp_wrong_branch(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(ref='refs/heads/not_primary')
        response = self.client.post(
            '/gh/mirror/ksp', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'Wrong branch'})

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp2_wrong_branch(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(ref='refs/heads/not_primary')
        response = self.client.post(
            '/gh/mirror/ksp2', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'Wrong branch'})

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp_no_commits(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(commits=[])
        response = self.client.post(
            '/gh/mirror/ksp', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'No commits received'})

    @mock.patch('netkan.webhooks.github_utils.sig_match')
    def test_inflate_ksp2_no_commits(self, sig: MagicMock):
        sig.return_value = True
        data = self.mock_netkan_hook()
        data.update(commits=[])
        response = self.client.post(
            '/gh/mirror/ksp2', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(response.json, {'message': 'No commits received'})


class TestWebhookInflate(WebhooksHarness):

    def setUp(self) -> None:
        super().setUp()
        queue_url = mock.patch(
            'netkan.webhooks.config.WebhooksConfig.inflation_queue', inflation_queue)
        queue_url.start()

    @staticmethod
    def mock_netkan_hook() -> dict:
        return {
            'identifiers': ['DogeCoinFlag'],
        }

    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp(self, queued: MagicMock):
        response = self.client.post(
            '/inflate/ksp', json=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp',
        )
        self.assertEqual(call[2].get('QueueUrl'), 'ksp.queue.url')

    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp2(self, queued: MagicMock):
        response = self.client.post(
            '/inflate/ksp2', json=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp2',
        )
        self.assertEqual(call[2].get('QueueUrl'), 'ksp2.queue.url')

    def test_inflate_ksp_no_identifiers(self):
        data = self.mock_netkan_hook()
        data.update(identifiers=[])
        response = self.client.post(
            '/inflate/ksp', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.text, 'An array of identifiers is required')

    def test_inflate_ksp2_no_identifiers(self):
        data = self.mock_netkan_hook()
        data.update(identifiers=[])
        response = self.client.post(
            '/inflate/ksp2', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.text, 'An array of identifiers is required')


class TestWebhookSpaceDockInflate(WebhooksHarness):

    def setUp(self) -> None:
        super().setUp()
        queue = MagicMock()
        queue.url = 'some.queue.url'
        queue_url = mock.patch(
            'netkan.webhooks.config.WebhooksConfig.inflation_queue', queue)
        queue_url.start()

    @staticmethod
    def mock_netkan_hook() -> dict:
        return {
            'mod_id': '777',
            'event_type': 'update',
        }

    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp(self, queued: MagicMock):
        response = self.client.post(
            '/sd/inflate/ksp', data=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp',
        )

    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp2(self, queued: MagicMock):
        response = self.client.post(
            '/sd/inflate/ksp2', data=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp2',
        )

    def test_inflate_ksp_no_identifiers(self):
        data = self.mock_netkan_hook()
        data.update(mod_id='ABC')
        response = self.client.post(
            '/sd/inflate/ksp', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.text, 'No such module')

    def test_inflate_ksp2_invalid_id(self):
        data = self.mock_netkan_hook()
        data.update(mod_id='ABC')
        response = self.client.post(
            '/sd/inflate/ksp2', json=data, follow_redirects=True)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.text, 'No such module')

    def test_inflate_delete(self):
        data = self.mock_netkan_hook()
        data.update(event_type='delete')
        response = self.client.post(
            '/sd/inflate/ksp', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 204)

    def test_inflate_ksp_locked(self):
        data = self.mock_netkan_hook()
        data.update(event_type='locked')
        response = self.client.post(
            '/sd/inflate/ksp', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 204)

    def test_inflate_ksp_unlocked(self):
        data = self.mock_netkan_hook()
        data.update(event_type='unlocked')
        response = self.client.post(
            '/sd/inflate/ksp', data=data, follow_redirects=True)
        self.assertEqual(response.status_code, 204)


class TestWebhookSpaceDockAdd(WebhooksHarness):

    def setUp(self) -> None:
        super().setUp()
        queue = MagicMock()
        queue.url = 'some.queue.url'
        queue_url = mock.patch(
            'netkan.webhooks.config.WebhooksConfig.add_queue', queue)
        queue_url.start()

    @staticmethod
    def mock_netkan_hook() -> dict:
        return {
            'name:              Mod Name Entered by the User on spacedock'
            'id': '12345',
            'license': 'GPL-3.0',
            'username': 'modauthor1',
            'email': 'modauthor1@gmail.com',
            'short_description': 'A mod that you should definitely install',
            'description': 'A mod that you should definitely install, and so on and so on',
            'site_name': 'SpaceDock',
        }

    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp(self, queued: MagicMock):
        response = self.client.post(
            '/sd/add/ksp', data=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp',
        )

    @mock.patch('netkan.webhooks.config.WebhooksConfig.client')
    def test_inflate_ksp2(self, queued: MagicMock):
        response = self.client.post(
            '/sd/add/ksp2', data=self.mock_netkan_hook(), follow_redirects=True)
        self.assertEqual(response.status_code, 204)
        call = queued.method_calls.pop().call_list().pop()
        self.assertEqual(
            call[2].get('Entries')[0].get('MessageAttributes').get(
                'GameId').get('StringValue'),
            'ksp2',
        )
