import click
import boto3
import datetime
import json
import logging
import time
from pathlib import Path
from .utils import init_repo, init_ssh
from .github import GitHubPR
from .indexer import MessageHandler
from .scheduler import NetkanScheduler
from .status import ModStatus
from .download_counter import DownloadCounter


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
def indexer(queue, metadata, token, repo, user, key,
            debug, timeout):
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
@click.option(
    '--dev', is_flag=True, default=False,
    help='Disable AWS Credit Checks',
)
@click.option(
    '--schedule-all', is_flag=True, default=False,
    help='Schedule all modules even if we think they should be covered by webhooks'
)
def scheduler(queue, netkan, max_queued, debug, dev, schedule_all):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
    )
    logging.info('Scheduler started at log level %s', level)

    scheduler = NetkanScheduler(Path('/tmp/NetKAN'), queue, force_all=schedule_all)
    if scheduler.can_schedule(max_queued, dev):
        init_repo(netkan, '/tmp/NetKAN')
        scheduler.schedule_all_netkans()
        logging.info("NetKANs submitted to {}".format(queue))


@click.command()
@click.option(
    '--status-bucket', envvar='STATUS_BUCKET', required=True,
    help='Bucket to Dump status.json'
)
@click.option(
    '--status-key', envvar='STATUS_KEY', default='status/netkan.json',
    help='Overwrite bucket key, defaults to `status/netkan.json`'
)
@click.option(
    '--interval', envvar='STATUS_INTERVAL', default=300,
    help='Dump status to S3 every `interval` seconds'
)
def export_status_s3(status_bucket, status_key, interval):
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s',
        level=logging.INFO
    )
    frequency = 'every {} seconds'.format(
        interval) if interval else 'once'
    logging.info('Exporting to s3://{}/{} {}'.format(
        status_bucket, status_key, frequency)
    )
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
    '--cluster', help='ECS Cluster running the service'
)
@click.option(
    '--service-name', help='Name of ECS Service to restart'
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
    '--days', help='Purge items older than X from cache'
)
def clean_cache(days):
    older_than = (
        datetime.datetime.now() - datetime.timedelta(days=int(days))
    ).timestamp()
    click.echo('Checking cache for files older than {} days'.format(days))
    for item in Path('/home/netkan/ckan_cache/').glob('*'):
        if item.is_file() and item.stat().st_mtime < older_than:
            click.echo('Purging {} from ckan cache'.format(
                item.name
            ))
            item.unlink()


@click.command()
@click.option(
    '--netkan', envvar='NETKAN_REPO',
    help='Path/URL/SSH to NetKAN repo for mod list',
)
@click.option(
    '--ckan-meta', envvar='CKANMETA_REPO',
    help='Path/URL/SSH to CKAN-meta repo for output',
)
@click.option(
    '--token', envvar='GH_Token', required=True,
    help='GitHub token for API calls',
)
@click.option('--key', envvar='SSH_KEY', required=True)
@click.option(
    '--debug', is_flag=True, default=False,
    help='Enable debug logging',
)
def download_counter(netkan, ckan_meta, token, key, debug):
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
    )
    logging.info('Download Counter started at log level %s', level)
    init_ssh(key, '/home/netkan/.ssh')
    init_repo(netkan, '/tmp/NetKAN')
    meta = init_repo(ckan_meta, '/tmp/CKAN-meta')
    logging.info('Starting Download Count Calculation...')
    DownloadCounter(
        '/tmp/NetKAN',
        meta,
        token
    ).update_counts()
    logging.info('Download Counter completed!')


netkan.add_command(indexer)
netkan.add_command(scheduler)
netkan.add_command(dump_status)
netkan.add_command(export_status_s3)
netkan.add_command(restore_status)
netkan.add_command(redeploy_service)
netkan.add_command(clean_cache)
netkan.add_command(download_counter)
