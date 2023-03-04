from typing import List, Iterable, IO, TYPE_CHECKING

import requests
import github
from git import Repo

from .metadata import Netkan
from .repos import NetkanRepo

if TYPE_CHECKING:
    from mypy_boto3_sqs.service_resource import Message
    from mypy_boto3_sqs.type_defs import (
        DeleteMessageBatchRequestEntryTypeDef,
        SendMessageBatchRequestEntryTypeDef,
    )
else:
    Message = object
    DeleteMessageBatchRequestEntryTypeDef = object
    SendMessageBatchRequestEntryTypeDef = object


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
