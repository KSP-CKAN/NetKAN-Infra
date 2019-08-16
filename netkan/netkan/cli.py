import click
import logging
import boto3
from pathlib import Path
from .utils import init_repo, init_ssh
from .github import GitHubPR
from .indexer import MessageHandler
from .scheduler import NetkanScheduler

@click.group()
def netkan():
    pass

@click.command()
@click.option(
    '--queue', envvar='SQS_QUEUE',
    help='SQS Queue to poll for metadata'
)
@click.option(
    '--metadata', envvar='METADATA_PATH',
    help='Path/URL/SSH to Metadata Repo',
)
@click.option(
    '--token', help='GitHub Token for PRs',
    required=True, envvar='GH_Token'
)
@click.option(
    '--repo', envvar='METADATA_REPO',
    help='GitHub repo to raise PR against (Org Repo: CKAN-meta)',
)
@click.option(
    '--user', envvar='METADATA_USER',
    help='GitHub user/org repo resides under (Org User: KSP-CKAN)',
)
@click.option(
    '--debug', is_flag=True, default=False,
    help='Enable debug logging',
)
@click.option(
    '--timeout', default=300, envvar='SQS_TIMEOUT',
    help='Reduce message visibility timeout for testing',
)
@click.option('--key', envvar='SSH_KEY', required=True)
def indexer(queue, metadata, token, repo, user, key, debug, timeout):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
    )
    init_ssh(key, '/home/netkan/.ssh')
    ckan_meta = init_repo(metadata, '/tmp/CKAN-meta')

    logging.info('Indexer started at log level %s', level)
    github_pr = GitHubPR(token, repo, user)
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=queue)
    logging.info('Opening git repo at {}'.format(ckan_meta.working_dir))

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


@click.command()
@click.option(
    '--queue', envvar='SQS_QUEUE',
    help='SQS Queue to send netkan metadata for scheduling'
)
@click.option(
    '--netkan', envvar='NETKAN_PATH',
    help='Path/URL to NetKAN Repo for dev override',
)
@click.option(
    '--max-queued', default=20, envvar='MAX_QUEUED',
    help='SQS Queue to send netkan metadata for scheduling'
)
@click.option(
    '--debug', is_flag=True, default=False,
    help='Enable debug logging',
)
def scheduler(queue, netkan, max_queued, debug):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
    )
    init_repo(netkan, '/tmp/NetKAN')

    logging.info('Scheduler started at log level %s', level)

    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=queue)
    client = boto3.client('sqs')

    message_count = int(queue.attributes.get('ApproximateNumberOfMessages', 0))
    if message_count > max_queued:
        logging.info(
            "Run skipped, too many NetKANs left to process ({} left)".format(
                message_count
            )
        )

    scheduler = NetkanScheduler(Path('/tmp/NetKAN'), queue.url, client)
    scheduler.schedule_all_netkans()

netkan.add_command(indexer)
netkan.add_command(scheduler)
