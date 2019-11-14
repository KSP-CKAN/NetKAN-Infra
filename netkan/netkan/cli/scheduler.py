import logging
from pathlib import Path
import click

from ..scheduler import NetkanScheduler
from ..utils import init_repo


@click.command()
@click.option(
    '--queue', envvar='SQS_QUEUE',
    help='SQS Queue to send netkan metadata for scheduling'
)
@click.option(
    '--netkan-remote', '--netkan', envvar='NETKAN_REMOTE',
    help='Path/URL to NetKAN Repo for dev override',
)
@click.option(
    '--max-queued', default=20, envvar='MAX_QUEUED',
    help='SQS Queue to send netkan metadata for scheduling'
)
@click.option(
    '--dev', is_flag=True, default=False,
    help='Disable AWS Credit Checks',
)
@click.option(
    '--group',
    type=click.Choice(['all', 'webhooks', 'nonhooks']), default="nonhooks",
    help='Which mods to schedule'
)
@click.option(
    '--min-credits', default=200,
    help='Only schedule if we have at least this many credits remaining'
)
def scheduler(queue, netkan_remote, max_queued, dev, group, min_credits):
    sched = NetkanScheduler(
        Path('/tmp/NetKAN'), queue,
        nonhooks_group=(group == 'all' or group == 'nonhooks'),
        webhooks_group=(group == 'all' or group == 'webhooks'),
    )
    if sched.can_schedule(max_queued, dev, min_credits):
        init_repo(netkan_remote, '/tmp/NetKAN')
        sched.schedule_all_netkans()
        logging.info("NetKANs submitted to %s", queue)
