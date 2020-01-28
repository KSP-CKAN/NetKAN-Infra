from .metadata import Netkan


def netkans(path, ids):
    return (Netkan(f'{path}/NetKAN/{id}.netkan') for id in ids)


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
