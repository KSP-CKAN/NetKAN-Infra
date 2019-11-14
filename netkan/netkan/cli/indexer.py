import logging
import click
import boto3

from ..indexer import MessageHandler
from ..github_pr import GitHubPR
from ..utils import init_repo, init_ssh


@click.command()
@click.option(
    '--queue', envvar='SQS_QUEUE',
    help='SQS Queue to poll for metadata'
)
@click.option(
    '--metadata', envvar='CKANMETA_REMOTE',
    help='Path/URL/SSH to Metadata Repo',
)
@click.option(
    '--token', help='GitHub Token for PRs',
    required=True, envvar='GH_Token'
)
@click.option(
    '--repo', envvar='CKANMETA_REPO',
    help='GitHub repo to raise PR against (Org Repo: CKAN-meta)',
)
@click.option(
    '--user', envvar='CKANMETA_USER',
    help='GitHub user/org repo resides under (Org User: KSP-CKAN)',
)
@click.option(
    '--timeout', default=300, envvar='SQS_TIMEOUT',
    help='Reduce message visibility timeout for testing',
)
@click.option('--key', envvar='SSH_KEY', required=True)
def indexer(queue, metadata, token, repo, user, key, timeout):
    init_ssh(key, '/home/netkan/.ssh')
    ckan_meta = init_repo(metadata, '/tmp/CKAN-meta')

    github_pr = GitHubPR(token, repo, user)
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=queue)
    logging.info('Opening git repo at %s', ckan_meta.working_dir)

    while True:
        messages = queue.receive_messages(
            MaxNumberOfMessages=10,
            MessageAttributeNames=['All'],
            VisibilityTimeout=timeout
        )
        if not messages:
            continue
        with MessageHandler(ckan_meta, github_pr) as handler:
            for message in messages:
                handler.append(message)
            handler.process_ckans()
            queue.delete_messages(
                Entries=handler.sqs_delete_entries()
            )
