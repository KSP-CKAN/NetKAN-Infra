import logging

from typing import Dict, List, Type, TYPE_CHECKING, Union
from types import TracebackType

import boto3

from .repos import CkanMetaRepo, NetkanRepo
from .cli.common import Game, SharedArgs

if TYPE_CHECKING:
    from mypy_boto3_sqs.service_resource import Message
    from mypy_boto3_sqs.type_defs import (
        DeleteMessageBatchRequestEntryTypeDef,
    )
else:
    Game = object
    Message = object
    DeleteMessageBatchRequestEntryTypeDef = object


class BaseMessageHandler:
    STRATEGY_OPTION = 'ours'
    game: Game

    def __init__(self, game: Game) -> None:
        self.game = game

    # Apparently gitpython can be leaky on long running processes
    # we can ensure we call close on it and run our handler inside
    # a context manager
    def __enter__(self) -> 'BaseMessageHandler':
        if not self.repo.is_active_branch('master'):
            self.repo.checkout_branch('master')
        self.repo.pull_remote_branch(
            'master', strategy_option=self.STRATEGY_OPTION)
        return self

    def __exit__(self, exc_type: Type[BaseException],
                 exc_value: BaseException, traceback: TracebackType) -> None:
        self.repo.close_repo()

    @property
    def repo(self) -> Union[CkanMetaRepo, NetkanRepo]:
        raise NotImplementedError

    def append(self, message: Message) -> None:
        raise NotImplementedError

    def process_messages(self) -> None:
        raise NotImplementedError

    def sqs_delete_entries(self) -> List[DeleteMessageBatchRequestEntryTypeDef]:
        raise NotImplementedError


class QueueHandler:
    common: SharedArgs
    _game_handlers: Dict[str, BaseMessageHandler]
    _handler_class: Type[BaseMessageHandler] = BaseMessageHandler

    def __init__(self, common: SharedArgs) -> None:
        self.common = common

    @property
    def game_handlers(self) -> Dict[str, BaseMessageHandler]:
        if getattr(self, '_game_handlers', None) is None:
            self._game_handlers = {}
        return self._game_handlers

    def game_handler(self, game_id: str) -> BaseMessageHandler:
        if self.game_handlers.get(game_id, None) is None:
            self.game_handlers.update({
                game_id: self._handler_class(self.common.game(game_id))
            })
        return self.game_handlers[game_id]

    def append_message(self, game_id: str, message: Message) -> None:
        self.game_handler(game_id).append(message)

    def run(self) -> None:
        sqs = boto3.resource('sqs')
        queue = sqs.get_queue_by_name(QueueName=self.common.queue)
        while True:
            messages = queue.receive_messages(
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All'],
                VisibilityTimeout=self.common.timeout
            )
            if not messages:
                continue
            for message in messages:
                game_id = message.message_attributes.get(  # type: ignore[union-attr,call-overload]
                    'GameId', {}).get('StringValue', None)
                if game_id is None:
                    logging.error('GameId missing from MessageAttributes')
                    continue
                self.append_message(game_id, message)

            for _, handler in self.game_handlers.items():
                with handler:
                    handler.process_messages()
                queue.delete_messages(
                    Entries=handler.sqs_delete_entries()
                )
