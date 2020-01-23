import sys
import datetime
import json
import logging
import time
from pathlib import Path
import boto3
import click

from .utils import init_repo, init_ssh
from .notifications import setup_log_handler, catch_all
from .github_pr import GitHubPR
from .indexer import MessageHandler
from .scheduler import NetkanScheduler
from .status import ModStatus
from .download_counter import DownloadCounter
from .ticket_closer import TicketCloser
from .auto_freezer import AutoFreezer
from .spacedock_adder import SpaceDockAdder


@click.option(
    '--debug', is_flag=True, default=False,
    help='Enable debug logging',
)
@click.group()
def netkan(debug):
    # Set up Discord logger so we can see errors
    if setup_log_handler(debug):
        # Catch uncaught exceptions and log them
        sys.excepthook = catch_all


@click.command()
@click.option(
    '--queue', envvar='SQS_QUEUE', required=True,
    help='SQS Queue to poll for metadata',
)
@click.option(
    '--ckanmeta-remote', '--metadata', envvar='CKANMETA_REMOTE', required=True,
    help='Path/URL/SSH to Metadata Repo',
)
@click.option(
    '--token', envvar='GH_Token', required=True,
    help='GitHub Token for PRs',
)
@click.option(
    '--repo', envvar='CKANMETA_REPO', required=True,
    help='GitHub repo to raise PR against (Org Repo: CKAN-meta)',
)
@click.option(
    '--user', envvar='CKANMETA_USER', required=True,
    help='GitHub user/org repo resides under (Org User: KSP-CKAN)',
)
@click.option(
    '--timeout', default=300, envvar='SQS_TIMEOUT',
    help='Reduce message visibility timeout for testing',
)
@click.option(
    '--key', envvar='SSH_KEY', required=True,
    help='SSH key for accessing repositories',
)
def indexer(queue, ckanmeta_remote, token, repo, user, key, timeout):
    init_ssh(key,  Path(Path.home(), '.ssh'))
    ckan_meta = init_repo(ckanmeta_remote, '/tmp/CKAN-meta')

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


@click.command()
@click.option(
    '--queue', envvar='SQS_QUEUE', required=True,
    help='SQS Queue to send netkan metadata for scheduling',
)
@click.option(
    '--netkan-remote', '--netkan', envvar='NETKAN_REMOTE', required=True,
    help='Path/URL to NetKAN Repo for dev override',
)
@click.option(
    '--ckanmeta-remote', envvar='CKANMETA_REMOTE', required=True,
    help='Path/URL/SSH to Metadata Repo',
)
@click.option(
    '--key', envvar='SSH_KEY', required=True,
    help='SSH key for accessing repositories',
)
@click.option(
    '--max-queued', default=20, envvar='MAX_QUEUED',
    help='SQS Queue to send netkan metadata for scheduling',
)
@click.option(
    '--dev', is_flag=True, default=False,
    help='Disable AWS Credit Checks',
)
@click.option(
    '--group',
    type=click.Choice(['all', 'webhooks', 'nonhooks']), default="nonhooks",
    help='Which mods to schedule',
)
@click.option(
    '--min-credits', default=200,
    help='Only schedule if we have at least this many credits remaining',
)
def scheduler(queue, netkan_remote, ckanmeta_remote, key, max_queued, dev, group, min_credits):
    init_ssh(key, Path(Path.home(), '.ssh'))
    sched = NetkanScheduler(
        Path('/tmp/NetKAN'), Path('/tmp/CKAN-meta'), queue,
        nonhooks_group=(group == 'all' or group == 'nonhooks'),
        webhooks_group=(group == 'all' or group == 'webhooks'),
    )
    if sched.can_schedule(max_queued, dev, min_credits):
        init_repo(netkan_remote, '/tmp/NetKAN')
        init_repo(ckanmeta_remote, '/tmp/CKAN-meta')
        sched.schedule_all_netkans()
        logging.info("NetKANs submitted to %s", queue)


@click.command()
@click.option(
    '--status-bucket', envvar='STATUS_BUCKET', required=True,
    help='Bucket to Dump status.json',
)
@click.option(
    '--status-key', envvar='STATUS_KEY', default='status/netkan.json',
    help='Overwrite bucket key, defaults to `status/netkan.json`',
)
@click.option(
    '--interval', envvar='STATUS_INTERVAL', default=300,
    help='Dump status to S3 every `interval` seconds',
)
def export_status_s3(status_bucket, status_key, interval):
    frequency = 'every {} seconds'.format(
        interval) if interval else 'once'
    logging.info('Exporting to s3://%s/%s %s',
                 status_bucket, status_key, frequency)
    while True:
        ModStatus.export_to_s3(status_bucket, status_key, interval)
        if not interval:
            break
        time.sleep(interval)
    logging.info('Done.')


@click.command()
def dump_status():
    click.echo(json.dumps(ModStatus.export_all_mods()))


@click.command()
@click.argument('filename')
def restore_status(filename):
    click.echo(
        'To keep within free tier rate limits, this could take some time'
    )
    ModStatus.restore_status(filename)
    click.echo('Done!')


@click.command()
@click.option(
    '--ckanmeta-remote', required=True, envvar='CKANMETA_REMOTE',
    help='Path/URL/SSH to Metadata Repo',
)
def recover_status_timestamps(ckanmeta_remote):
    ModStatus.recover_timestamps(init_repo(ckanmeta_remote, '/tmp/CKAN-meta'))


@click.command()
@click.option(
    '--cluster', help='ECS Cluster running the service',
)
@click.option(
    '--service-name', help='Name of ECS Service to restart',
)
def redeploy_service(cluster, service_name):
    click.secho(
        'Forcing redeployment of {}:{}'.format(cluster, service_name),
        fg='green'
    )
    client = boto3.client('ecs')
    services = client.list_services(maxResults=100,
                                    cluster=cluster)['serviceArns']
    try:
        service = list(filter(lambda i: service_name in i, services))[0]
    except IndexError:
        available = '\n    - '.join(
            [f.split('/')[1].split('-')[1] for f in services]
        )
        raise click.UsageError(
            "Service '{}' not found. Available services:\n    - {}".format(
                service, available)
        )
    client.update_service(
        cluster=cluster,
        service=service,
        forceNewDeployment=True
    )
    click.secho('Waiting for service to become stable...', fg='green')
    waiter = client.get_waiter('services_stable')
    waiter.wait(
        cluster=cluster,
        services=[service]
    )
    click.secho('Service Redeployed', fg='green')


@click.command()
@click.option(
    '--days', help='Purge items older than X from cache',
)
@click.option(
    '--cache', envvar='NETKAN_CACHE', default=str(Path.home()) + '/ckan_cache/',
    type=click.Path(exists=True, writable=True),
    help='Absolute path to the mod download cache'
)
def clean_cache(days, cache):
    older_than = (
        datetime.datetime.now() - datetime.timedelta(days=int(days))
    ).timestamp()
    click.echo('Checking cache for files older than {} days'.format(days))
    for item in Path(cache).glob('*'):
        if item.is_file() and item.stat().st_mtime < older_than:
            click.echo('Purging {} from ckan cache'.format(
                item.name
            ))
            item.unlink()


@click.command()
@click.option(
    '--netkan-remote', '--netkan', envvar='NETKAN_REMOTE', required=True,
    help='Path/URL/SSH to NetKAN repo for mod list',
)
@click.option(
    '--ckanmeta-remote', '--ckan-meta', envvar='CKANMETA_REMOTE', required=True,
    help='Path/URL/SSH to CKAN-meta repo for output',
)
@click.option(
    '--token', envvar='GH_Token', required=True,
    help='GitHub token for API calls',
)
@click.option(
    '--key', envvar='SSH_KEY', required=True,
    help='SSH key for accessing repositories',
)
def download_counter(netkan_remote, ckanmeta_remote, token, key):
    init_ssh(key, Path(Path.home(), '.ssh'))
    init_repo(netkan_remote, '/tmp/NetKAN')
    meta = init_repo(ckanmeta_remote, '/tmp/CKAN-meta')
    logging.info('Starting Download Count Calculation...')
    DownloadCounter(
        '/tmp/NetKAN',
        meta,
        token
    ).update_counts()
    logging.info('Download Counter completed!')


@click.command()
@click.option(
    '--token', required=True, envvar='GH_Token',
    help='GitHub token for querying and closing issues',
)
@click.option(
    '--days-limit', default=7,
    help='Number of days to wait for OP to reply',
)
def ticket_closer(token, days_limit):
    TicketCloser(token).close_tickets(days_limit)


@click.command()
@click.option(
    '--netkan-remote', '--netkan', envvar='NETKAN_REMOTE', required=True,
    help='Path/URL/SSH to NetKAN repo for mod list',
)
@click.option(
    '--token', required=True, envvar='GH_Token',
    help='GitHub token for querying and closing issues',
)
@click.option(
    '--repo', envvar='NETKAN_REPO', required=True,
    help='GitHub repo to raise PR against (Org Repo: NetKAN)',
)
@click.option(
    '--user', envvar='NETKAN_USER', required=True,
    help='GitHub user/org repo resides under (Org User: KSP-CKAN)',
)
@click.option(
    '--days-limit', default=1000,
    help='Number of days to wait before freezing a mod as idle',
)
@click.option(
    '--key', envvar='SSH_KEY', required=True,
    help='SSH key for accessing repositories',
)
def auto_freezer(netkan_remote, token, repo, user, days_limit, key):
    init_ssh(key, Path(Path.home(), '.ssh'))
    af = AutoFreezer(
        init_repo(netkan_remote, '/tmp/NetKAN'),
        GitHubPR(token, repo, user)
    )
    af.freeze_idle_mods(days_limit)
    af.mark_frozen_mods()


@click.command()
@click.option(
    '--queue', envvar='SQS_QUEUE',
    help='SQS Queue to send netkan metadata for inflation',
    required=True,
)
@click.option(
    '--timeout', default=300, envvar='SQS_TIMEOUT',
    help='Reduce message visibility timeout for testing',
)
@click.option(
    '--netkan-remote', '--netkan', envvar='NETKAN_REMOTE',
    help='Path/URL to NetKAN Repo for dev override',
)
@click.option(
    '--token', help='GitHub Token for PRs',
    required=True, envvar='GH_Token'
)
@click.option(
    '--repo', envvar='NETKAN_REPO',
    help='GitHub repo to raise PR against (Org Repo: CKAN-meta)',
)
@click.option(
    '--user', envvar='NETKAN_USER',
    help='GitHub user/org repo resides under (Org User: KSP-CKAN)',
)
@click.option(
    '--key', envvar='SSH_KEY', required=True,
    help='SSH key for accessing repositories',
)
def spacedock_adder(queue, timeout, netkan_remote, token, repo, user, key):
    init_ssh(key,  Path(Path.home(), '.ssh'))
    sd_adder = SpaceDockAdder(
        queue,
        timeout,
        init_repo(netkan_remote, "/tmp/NetKAN"),
        GitHubPR(token, repo, user)
    )
    sd_adder.run()


netkan.add_command(indexer)
netkan.add_command(scheduler)
netkan.add_command(dump_status)
netkan.add_command(export_status_s3)
netkan.add_command(restore_status)
netkan.add_command(recover_status_timestamps)
netkan.add_command(redeploy_service)
netkan.add_command(clean_cache)
netkan.add_command(download_counter)
netkan.add_command(ticket_closer)
netkan.add_command(auto_freezer)
netkan.add_command(spacedock_adder)
