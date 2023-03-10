from typing import TYPE_CHECKING

import boto3

from ..cli.common import SharedArgs


if TYPE_CHECKING:
    from mypy_boto3_sqs.client import SQSClient
    from mypy_boto3_sqs.service_resource import Queue
else:
    SQSClient = object
    Queue = object


class WebhooksConfig:
    _client: SQSClient
    _add_queue: Queue
    _mirror_queue: Queue

    # pylint: disable=attribute-defined-outside-init

    # Ideally this would be __init__, but we want other modules to
    # import a reference to our global config object before we set
    # its properties, and that requires a temporary 'empty' state.
    def setup(self, ssh_key: str, secret: str,
              netkan_remote: str, ckanmeta_remote: str,
              inf_queue_name: str, add_queue_name: str, mir_queue_name: str) -> None:

        self.secret = secret
        self.common = SharedArgs()
        self.common.ssh_key = ssh_key
        self.common.ckanmeta_remotes = tuple(ckanmeta_remote.split(' '))
        self.common.netkan_remotes = tuple(netkan_remote.split(' '))
        self.common.deep_clone = False
        self._inf_queue_name = inf_queue_name
        self._add_queue_name = add_queue_name
        self._mir_queue_name = mir_queue_name

    @property
    def client(self) -> SQSClient:
        if getattr(self, '_client', None) is None:
            self._client = boto3.client('sqs')
        return self._client

    def inflation_queue(self, game: str) -> Queue:
        game_id = game.lower()
        if getattr(self, f'_{game_id}_inflation_queue', None) is None:
            sqs = boto3.resource('sqs')
            setattr(self, f'_{game_id}_inflation_queue', sqs.get_queue_by_name(
                QueueName=self._inf_queue_name))
        return getattr(self, f'_{game_id}_inflation_queue')

    @property
    def add_queue(self) -> Queue:
        if getattr(self, '_add_queue', None) is None:
            sqs = boto3.resource('sqs')
            self._add_queue = sqs.get_queue_by_name(
                QueueName=self._add_queue_name)
        return self._add_queue

    @property
    def mirror_queue(self) -> Queue:
        if getattr(self, '_mirror_queue', None) is None:
            sqs = boto3.resource('sqs')
            self._mirror_queue = sqs.get_queue_by_name(
                QueueName=self._mir_queue_name)
        return self._mirror_queue


# Provide the active config to other modules
current_config = WebhooksConfig()
