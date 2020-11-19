import datetime
import json
import logging
import time

from pathlib import Path

import boto3
import click

from .common import common_options, pass_state, SharedArgs

from ..status import ModStatus
from ..download_counter import DownloadCounter
from ..ticket_closer import TicketCloser
from ..auto_freezer import AutoFreezer
from ..mirrorer import Mirrorer


@click.command()
@click.option(
    '--days-limit', default=1000,
    help='Number of days to wait before freezing a mod as idle',
)
@click.option(
    '--days-till-ignore', default=21,
    help='Mods idle this many days will be ignored',
)
@common_options
@pass_state
def auto_freezer(common: SharedArgs, days_limit: int, days_till_ignore: int) -> None:
    afr = AutoFreezer(
        common.netkan_repo,
        common.github_pr,
    )
    afr.freeze_idle_mods(days_limit, days_till_ignore)
    afr.mark_frozen_mods()


@click.command()
@common_options
@pass_state
def download_counter(common: SharedArgs) -> None:
    logging.info('Starting Download Count Calculation...')
    DownloadCounter(
        common.netkan_repo,
        common.ckanmeta_repo,
        common.token
    ).update_counts()
    logging.info('Download Counter completed!')


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
def export_status_s3(status_bucket: str, status_key: str, interval: bool) -> None:
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
def dump_status() -> None:
    click.echo(json.dumps(ModStatus.export_all_mods()))


@click.command()
@click.argument('filename')
def restore_status(filename: str) -> None:
    click.echo(
        'To keep within free tier rate limits, this could take some time'
    )
    ModStatus.restore_status(filename)
    click.echo('Done!')


@click.command()
@common_options
@pass_state
def recover_status_timestamps(common: SharedArgs) -> None:
    ModStatus.recover_timestamps(common.ckanmeta_repo)


@click.command()
@click.option(
    '--cluster', help='ECS Cluster running the service',
)
@click.option(
    '--service-name', help='Name of ECS Service to restart',
)
def redeploy_service(cluster: str, service_name: str) -> None:
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
                service_name, available)
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
    '--days-limit', default=7,
    help='Number of days to wait for OP to reply',
)
@common_options
@pass_state
def ticket_closer(common: SharedArgs, days_limit: int) -> None:
    TicketCloser(common.token).close_tickets(days_limit)


@click.command()
@click.option(
    '--days', help='Purge items older than X from cache',
)
@click.option(
    '--cache', envvar='NETKAN_CACHE', default=str(Path.home()) + '/ckan_cache/',
    type=click.Path(exists=True, writable=True),
    help='Absolute path to the mod download cache'
)
def clean_cache(days: int, cache: str) -> None:
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
    '--dry-run',
    help='',
    default=False,
)
@common_options
@pass_state
def mirror_purge_epochs(common: SharedArgs, dry_run: bool) -> None:
    Mirrorer(
        common.ckanmeta_repo, common.ia_access,
        common.ia_secret, common.ia_collection
    ).purge_epochs(dry_run)
