import logging

import click

from .common import common_options, pass_state, SharedArgs

from ..indexer import IndexerQueueHandler
from ..scheduler import NetkanScheduler
from ..spacedock_adder import SpaceDockAdderQueueHandler
from ..mirrorer import Mirrorer


@click.command(short_help='The Indexer service')
@common_options
@pass_state
def indexer(common: SharedArgs) -> None:
    """
    Retrieves inflated metadata from the Inflator's output queue
    and updates the metadata repo as needed
    """
    IndexerQueueHandler(common).run()


@click.command(short_help='The Scheduler service')
@click.option(
    '--max-queued', default=20, envvar='MAX_QUEUED',
    help='SQS Queue to send netkan metadata for scheduling',
)
@click.option(
    '--group',
    type=click.Choice(['all', 'webhooks', 'nonhooks']), default="nonhooks",
    help='Which mods to schedule',
)
@click.option(
    '--min-cpu', default=200,
    help='Only schedule if we have at least this many CPU credits remaining',
)
@click.option(
    '--min-io', default=70,
    help='Only schedule if we have at least this many IO credits remaining',
)
@common_options
@pass_state
def scheduler(
    common: SharedArgs,
    max_queued: int,
    group: str,
    min_cpu: int,
    min_io: int
) -> None:
    """
    Reads netkans from a NetKAN repo and submits them to the
    Inflator's input queue
    """
    for game_id in common.game_ids:
        game = common.game(game_id)
        sched = NetkanScheduler(
            common, game.inflation_queue, common.token, game.name,
            nonhooks_group=(group in ('all', 'nonhooks')),
            webhooks_group=(group in ('all', 'webhooks')),
        )
        if sched.can_schedule(max_queued, common.dev, min_cpu, min_io):
            sched.schedule_all_netkans()
            logging.info("NetKANs submitted to %s", game.inflation_queue)


@click.command(short_help='The Mirrorer service')
@common_options
@pass_state
def mirrorer(common: SharedArgs) -> None:
    """
    Uploads redistributable mods to archive.org as they
    are added to the meta repo
    """
    # We need at least 50 mods for a collection for ksp2, keeping
    # to just ksp for now
    Mirrorer(
        common.game('ksp').ckanmeta_repo, common.ia_access, common.ia_secret,
        common.game('ksp').ia_collection, common.token
    ).process_queue(common.queue, common.timeout)


@click.command(short_help='The SpaceDockAdder service')
@common_options
@pass_state
def spacedock_adder(common: SharedArgs) -> None:
    """
    Submits pull requests to a NetKAN repo when users
    click the Add to CKAN checkbox on SpaceDock
    """
    SpaceDockAdderQueueHandler(common).run()
