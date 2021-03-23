from typing import List, Iterable, Dict, Any
import boto3  # pylint: disable=unused-import

import github
from git import Repo

from .metadata import Netkan
from .repos import NetkanRepo


def netkans(path: str, ids: Iterable[str]) -> Iterable[Netkan]:
    repo = NetkanRepo(Repo(path))
    return (Netkan(p) for p in repo.nk_paths(ids))


def sqs_batch_entries(messages: Iterable[Dict[str, str]],
                      batch_size: int = 10) -> Iterable[List[Dict[str, str]]]:
    batch = []
    for msg in messages:
        batch.append(msg)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if len(batch) > 0:
        yield batch


def pull_all(repos: Iterable[Repo]) -> None:
    for repo in repos:
        repo.remotes.origin.pull('master', strategy_option='theirs', depth='1', allow_unrelated_histories=True)
        repo.git.gc(prune='all')


def github_limit_remaining(token: str) -> int:
    return github.Github(token).get_rate_limit().core.remaining


def deletion_msg(msg: 'boto3.resources.factory.sqs.Message') -> Dict[str, Any]:
    return {
        'Id':            msg.message_id,
        'ReceiptHandle': msg.receipt_handle,
    }
