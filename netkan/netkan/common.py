import logging

from typing import Dict, List, Iterable, IO, Type, TYPE_CHECKING
from types import TracebackType

import boto3
import requests
import github
from git import Repo

from .metadata import Netkan
from .repos import CkanMetaRepo, NetkanRepo

if TYPE_CHECKING:
    from mypy_boto3_sqs.service_resource import Message
    from mypy_boto3_sqs.type_defs import (
        DeleteMessageBatchRequestEntryTypeDef,
        SendMessageBatchRequestEntryTypeDef,
    )
    from .cli.common import Game, SharedArgs
else:
    Game = object
    Message = object
    DeleteMessageBatchRequestEntryTypeDef = object
    SendMessageBatchRequestEntryTypeDef = object
    SharedArgs = object


USER_AGENT = 'Mozilla/5.0 (compatible; Netkanbot/1.0; CKAN; +https://github.com/KSP-CKAN/NetKAN-Infra)'


def netkans(path: str, ids: Iterable[str]) -> Iterable[Netkan]:
    repo = NetkanRepo(Repo(path))
    return (Netkan(p) for p in repo.nk_paths(ids))


def sqs_batch_entries(messages: Iterable[SendMessageBatchRequestEntryTypeDef],
                      batch_size: int = 10) -> Iterable[List[SendMessageBatchRequestEntryTypeDef]]:
    batch: List[SendMessageBatchRequestEntryTypeDef] = []
    for msg in messages:
        batch.append(msg)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if len(batch) > 0:
        yield batch


def pull_all(repos: Iterable[Repo]) -> None:
    for repo in repos:
        repo.remotes.origin.pull('master', strategy_option='theirs')


def github_limit_remaining(token: str) -> int:
    return github.Github(token, user_agent=USER_AGENT).get_rate_limit().core.remaining


def deletion_msg(msg: Message) -> DeleteMessageBatchRequestEntryTypeDef:
    return {
        'Id':            msg.message_id,
        'ReceiptHandle': msg.receipt_handle,
    }


def download_stream_to_file(download_url: str, dest_file: IO[bytes]) -> None:
    # Get big files in little chunks
    with requests.get(download_url,
                      headers={'User-Agent': USER_AGENT},
                      stream=True,
                      timeout=60) as req:
        for chunk in req.iter_content(chunk_size=8192):
            dest_file.write(chunk)


class BaseMessageHandler:
    game: Game

    def __init__(self, game: Game) -> None:
        self.game = game

    # Apparently gitpython can be leaky on long running processes
    # we can ensure we call close on it and run our handler inside
    # a context manager
    def __enter__(self) -> 'BaseMessageHandler':
        if not self.ckm_repo.is_active_branch('master'):
            self.ckm_repo.checkout_branch('master')
        self.ckm_repo.pull_remote_branch('master')
        return self

    def __exit__(self, exc_type: Type[BaseException],
                 exc_value: BaseException, traceback: TracebackType) -> None:
        self.ckm_repo.close_repo()

    @property
    def ckm_repo(self) -> CkanMetaRepo:
        return self.game.ckanmeta_repo

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

    def game_handler(self, game: str) -> BaseMessageHandler:
        if self.game_handlers.get(game, None) is None:
            self.game_handlers.update({
                game: self._handler_class(self.common.game(game))
            })
        return self.game_handlers[game]

    def append_message(self, game: str, message: Message) -> None:
        self.game_handler(game).append(message)

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
                game = message.message_attributes.get(  # type: ignore[union-attr,call-overload]
                    'GameId', {}).get('StringValue', None)
                if game is None:
                    logging.error('GameId missing from MessageAttributes')
                    continue
                self.append_message(game, message)

            for _, handler in self.game_handlers.items():
                with handler:
                    handler.process_messages()
                queue.delete_messages(
                    Entries=handler.sqs_delete_entries()
                )
