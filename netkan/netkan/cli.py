import click
import logging
import boto3
import sys
import subprocess
from git import Repo
from pathlib import Path
from .github import GitHubPR
from .indexer import MessageHandler


@click.command()
@click.option(
    '--queue', default='Outbound.fifo', envvar='SQS_QUEUE',
    help='SQS Queue to poll for metadata'
)
@click.option(
    '--metadata', default='git@github.com:KSP-CKAN/CKAN-meta.git',
    envvar='METADATA_PATH', help='Path/URL to Metadata Repo for dev override',
)
@click.option(
    '--token', help='GitHub Token for PRs',
    required=True, envvar='GH_Token'
)
@click.option(
    '--repo', default='CKAN-meta', envvar='METADATA_REPO',
    help='GitHub repo to raise PR against',
)
@click.option(
    '--user', default='KSP-CKAN', envvar='METADATA_USER',
    help='GitHub user/org repo resides under',
)
@click.option(
    '--debug', is_flag=True, default=False,
    help='Enable debug logging',
)
@click.option(
    '--timeout', default=300,
    help='Reduce message visibility timeout for testing',
)
@click.option('--key', envvar='SSH_KEY', required=True)
def indexer(queue, metadata, token, repo, user, key, debug, timeout):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
    )

    if not key:
        logging.error('Private Key required for SSH Git')
        sys.exit(1)
    logging.info('Private Key found, writing to disk')
    key_path = Path('/home/netkan/.ssh')
    key_path.mkdir(exist_ok=True)
    key_file = Path(key_path, 'id_rsa')
    if not key_file.exists():
        key_file.write_text('{}\n'.format(key))
        key_file.chmod(0o400)
        scan = subprocess.run([
            'ssh-keyscan', '-t', 'rsa', 'github.com'
        ], stdout=subprocess.PIPE)
        Path(key_path, 'known_hosts').write_text(scan.stdout.decode('utf-8'))

    clone_path = Path('/tmp/CKAN-meta')
    if not clone_path.exists():
        logging.info('Cloning metadata')
        Repo.clone_from(metadata, clone_path, depth=1)
    ckan_meta = Repo(clone_path)

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
