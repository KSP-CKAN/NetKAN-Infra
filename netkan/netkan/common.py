from git import Repo

from .metadata import Netkan
from .repos import NetkanRepo


def netkans(path, ids):
    repo = NetkanRepo(Repo(path))
    return (Netkan(p) for p in repo.nk_paths(ids))


def sqs_batch_entries(messages, batch_size=10):
    batch = []
    for msg in messages:
        batch.append(msg)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if len(batch) > 0:
        yield batch


def pull_all(repos):
    for repo in repos:
        repo.remotes.origin.pull('master', strategy_option='theirs')
