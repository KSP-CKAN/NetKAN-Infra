import sys
import click

from ..notifications import setup_log_handler, catch_all

from .indexer import indexer
from .scheduler import scheduler
from .dump_status import dump_status
from .export_status_s3 import export_status_s3
from .restore_status import restore_status
from .redeploy_service import redeploy_service
from .clean_cache import clean_cache
from .download_counter import download_counter
from .ticket_closer import ticket_closer


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


netkan.add_command(indexer)
netkan.add_command(scheduler)
netkan.add_command(dump_status)
netkan.add_command(export_status_s3)
netkan.add_command(restore_status)
netkan.add_command(redeploy_service)
netkan.add_command(clean_cache)
netkan.add_command(download_counter)
netkan.add_command(ticket_closer)
