import datetime
import json
import logging
import time
import io

from pathlib import Path
from typing import Tuple

import boto3
import click
from ruamel.yaml import YAML

from .common import common_options, pass_state, SharedArgs

from ..status import ModStatus
from ..download_counter import DownloadCounter
from ..ticket_closer import TicketCloser
from ..auto_freezer import AutoFreezer
from ..mirrorer import Mirrorer
from ..mod_analyzer import ModAnalyzer


@click.command(short_help='Submit or update a PR freezing idle mods')
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
    """
    Scan the given NetKAN repo for mods that haven't updated
    in a given number of days and submit or update a pull request to freeze them
    """
    for game_id in common.game_ids:
        afr = AutoFreezer(
            common.game(game_id).netkan_repo,
            common.game(game_id).github_pr,
            game_id,
        )
        afr.freeze_idle_mods(days_limit, days_till_ignore)
        afr.mark_frozen_mods()


@click.command(short_help='Update download counts in a given repo')
@common_options
@pass_state
def download_counter(common: SharedArgs) -> None:
    """
    Count downloads for all the mods in the given repo
    and update the download_counts.json file
    """
    for game_id in common.game_ids:
        logging.info('Starting Download Count Calculation (%s)...', game_id)
        DownloadCounter(game_id,
                        common.game(game_id).ckanmeta_repo,
                        common.token).update_counts()
        logging.info('Download Counter completed! (%s)', game_id)


@click.command(short_help='Autogenerate a mod\'s .netkan properties')
@click.argument('ident', required=True)
@click.argument('download_url', required=True)
@common_options
@pass_state
def analyze_mod(common: SharedArgs, ident: str, download_url: str) -> None:
    """
    Download a mod with identifier IDENT from DOWNLOAD_URL
    and guess its netkan properties
    """
    sio = io.StringIO()
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.dump(ModAnalyzer(ident, download_url, common.game(common.game_id or 'KSP'))
                  .get_netkan_properties(),
              sio)
    click.echo(f'identifier: {ident}')
    click.echo(sio.getvalue())


@click.command(short_help='Update the JSON status file on s3')
@click.option(
    '--status-bucket', envvar='STATUS_BUCKET', required=True,
    help='Bucket to Dump status.json',
)
@click.option(
    '--status-keys', envvar='STATUS_KEYS', default=['ksp=status/netkan.json'],
    help='Overwrite bucket key, defaults to `status/netkan.json`',
    multiple=True
)
@click.option(
    '--interval', envvar='STATUS_INTERVAL', default=300,
    help='Dump status to S3 every `interval` seconds',
)
def export_status_s3(status_bucket: str, status_keys: Tuple[str, ...], interval: int) -> None:
    """
    Retrieves the mod timestamps and warnings/errors from the status database
    and saves them where the status page can see them in JSON format
    """
    frequency = f'every {interval} seconds' if interval else 'once'
    while True:
        for status in status_keys:
            game_id, key = status.split('=')
            logging.info('Exporting %s to s3://%s/%s (%s)',
                         status_bucket, game_id, key, frequency)
            ModStatus.export_to_s3(
                bucket=status_bucket,
                key=key,
                game_id=game_id
            )
        if interval <= 0:
            break
        time.sleep(interval)
    logging.info('Done.')


@click.command(short_help='Print the mod status JSON')
def dump_status() -> None:
    """
    Retrieves the mod timestamps and warnings/errors from the status database
    and prints them in JSON format
    """
    click.echo(json.dumps(ModStatus.export_all_mods()))


@click.command(short_help='Normalize status database entries')
@click.argument('filename')
def restore_status(filename: str) -> None:
    """
    Normalize the status info for all mods in database and
    commit them in groups of 5 per second
    """
    click.echo(
        'To keep within free tier rate limits, this could take some time'
    )
    ModStatus.restore_status(filename)
    click.echo('Done!')


@click.command(short_help='Set status timestamps based on git repo')
@common_options
@pass_state
def recover_status_timestamps(common: SharedArgs) -> None:
    """
    If a mod's status entry is missing a last indexed timestamp,
    set it to the timstamp from the most recent commit in the meta repo
    """
    ModStatus.recover_timestamps(common.game(common.game_id).ckanmeta_repo)


@click.command(short_help='Update and restart one of the bot\'s containers')
@click.option(
    '--cluster', required=True,
    help='ECS Cluster running the service',
)
@click.option(
    '--service-name', required=True,
    help='Name of ECS Service to restart',
)
def redeploy_service(cluster: str, service_name: str) -> None:
    """
    Update and restart the given service on the given container
    """
    click.secho(
        f'Forcing redeployment of {cluster}:{service_name}',
        fg='green'
    )
    client = boto3.client('ecs')
    services = client.list_services(maxResults=100,
                                    cluster=cluster)['serviceArns']
    try:
        service = list(filter(lambda i: service_name in i, services))[0]
    except IndexError as exc:
        available = '\n    - '.join(
            [f.split('/')[1].split('-')[1] for f in services]
        )
        raise click.UsageError(
            f"Service '{service_name}' not found. Available services:\n    - {available}"
        ) from exc
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


@click.command(short_help='Close inactive issues on GitHub')
@click.option(
    '--days-limit', default=7,
    help='Number of days to wait for OP to reply',
)
@common_options
@pass_state
def ticket_closer(common: SharedArgs, days_limit: int) -> None:
    """
    Close issues with the Support tag where the most recent
    reply isn't from the original author and that have been
    inactive for the given number of days
    """
    TicketCloser(common.token, common.user).close_tickets(days_limit)


@click.command(short_help='Purge old downloads from the bot\'s download cache')
@click.option(
    '--days', help='Purge items older than X from cache',
)
@click.option(
    '--cache', envvar='NETKAN_CACHE', default=str(Path.home()) + '/ckan_cache/',
    type=click.Path(exists=True, writable=True),
    help='Absolute path to the mod download cache'
)
def clean_cache(days: int, cache: str) -> None:
    """
    Purge downloads from the bot's download cach that are
    older than the given number of days
    """
    older_than = (
        datetime.datetime.now() - datetime.timedelta(days=int(days))
    ).timestamp()
    click.echo(f'Checking cache for files older than {days} days')
    for item in Path(cache).glob('*'):
        if item.is_file() and item.stat().st_mtime < older_than:
            click.echo(f'Purging {item.name} from ckan cache')
            item.unlink()


@click.command(short_help='Remove epoch strings from archive.org entries')
@click.option(
    '--dry-run', default=False,
    help='True to report what would be done instead of doing it'
)
@common_options
@pass_state
def mirror_purge_epochs(common: SharedArgs, dry_run: bool) -> None:
    """
    Loop over mods mirrored to archive.org
    and remove their version epoch prefixes.
    This has never actually been used.
    """
    Mirrorer(
        common.game(common.game_id).ckanmeta_repo, common.ia_access,
        common.ia_secret, common.game(common.game_id).ia_collection
    ).purge_epochs(dry_run)
