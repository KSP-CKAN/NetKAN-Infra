import datetime
from pathlib import Path
import click


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
