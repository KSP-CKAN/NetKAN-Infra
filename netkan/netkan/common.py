from git import Repo
from typing import List, Iterable, Dict

from .metadata import Netkan
from .repos import NetkanRepo


def netkans(path: str, ids: Iterable[str]) -> Iterable[Netkan]:
    repo = NetkanRepo(Repo(path))
    return (Netkan(p) for p in repo.nk_paths(ids))


def sqs_batch_entries(messages: Iterable[Dict[str, str]], batch_size: int = 10) -> Iterable[List[Dict[str, str]]]:
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
        repo.remotes.origin.pull('master', strategy_option='theirs')
