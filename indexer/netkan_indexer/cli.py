import click
import logging
import boto3
from .github import GitHubPR
from .indexer import MessageHandler


@click.command()
@click.option(
    '--queue', default='OutboundDev.fifo',
    help='SQS Queue to poll for metadata'
)
@click.option(
    '--metadata', help='Path to Metadata Repo',
    required=True, envvar='METADATA_REPO'
)
@click.option(
    '--token', help='GitHub Token for PRs',
    required=True, envvar='GH_Token'
)
@click.option(
    '--repo', default='CKAN-meta',
    help='GitHub repo to raise PR against',
)
@click.option(
    # TODO: Set this correctly before release
    '--user', default='Techman83',
    help='GitHub user/org repo resides under',
)
@click.option(
    '--debug', is_flag=True, default=False,
    help='Enable debug logging',
)
def run(queue, metadata, token, repo, user, debug):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
    )
    logging.info("Indexer started at log level %s", level)

    github_pr = GitHubPR(token, repo, user)
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=queue)

    while True:
        messages = queue.receive_messages(
            MaxNumberOfMessages=10,
            VisibilityTimeout=300
        )
        if not messages:
            continue
        with MessageHandler(metadata, github_pr) as handler:
            for message in messages:
                handler.append(message)
            sqs.delete_batch(
                QueueUrl='string',
                Entries=handler.sqs_delete_entries
            )
