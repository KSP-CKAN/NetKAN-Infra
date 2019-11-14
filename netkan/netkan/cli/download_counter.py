import logging
import click

from ..download_counter import DownloadCounter
from ..utils import init_repo, init_ssh


@click.command()
@click.option(
    '--netkan-remote', '--netkan', envvar='NETKAN_REMOTE',
    help='Path/URL/SSH to NetKAN repo for mod list',
)
@click.option(
    '--ckan-meta', envvar='CKANMETA_REMOTE',
    help='Path/URL/SSH to CKAN-meta repo for output',
)
@click.option(
    '--token', envvar='GH_Token', required=True,
    help='GitHub token for API calls',
)
@click.option('--key', envvar='SSH_KEY', required=True)
def download_counter(netkan_remote, ckan_meta, token, key):
    init_ssh(key, '/home/netkan/.ssh')
    init_repo(netkan_remote, '/tmp/NetKAN')
    meta = init_repo(ckan_meta, '/tmp/CKAN-meta')
    logging.info('Starting Download Count Calculation...')
    DownloadCounter(
        '/tmp/NetKAN',
        meta,
        token
    ).update_counts()
    logging.info('Download Counter completed!')
