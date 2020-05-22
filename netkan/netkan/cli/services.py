import logging

import boto3
import click

from .common import common_options, pass_state

from ..indexer import MessageHandler
from ..scheduler import NetkanScheduler
from ..spacedock_adder import SpaceDockAdder
from ..mirrorer import Mirrorer


@click.command()
@common_options
@pass_state
def indexer(common):
    sqs = boto3.resource('sqs')
    queue = sqs.get_queue_by_name(QueueName=common.queue)

    while True:
        messages = queue.receive_messages(
            MaxNumberOfMessages=10,
            MessageAttributeNames=['All'],
            VisibilityTimeout=common.timeout
        )
        if not messages:
            continue
        with MessageHandler(common.ckanmeta_repo, common.github_pr) as handler:
            for message in messages:
                handler.append(message)
            handler.process_ckans()
            queue.delete_messages(
                Entries=handler.sqs_delete_entries()
            )


@click.command()
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
def scheduler(common, max_queued, group, min_cpu, min_io):
    sched = NetkanScheduler(
        common.netkan_repo, common.ckanmeta_repo, common.queue,
        nonhooks_group=(group == 'all' or group == 'nonhooks'),
        webhooks_group=(group == 'all' or group == 'webhooks'),
    )
    if sched.can_schedule(max_queued, common.dev, min_cpu, min_io):
        sched.schedule_all_netkans()
        logging.info("NetKANs submitted to %s", common.queue)


@click.command()
@common_options
@pass_state
def mirrorer(common):
    Mirrorer(
        common.ckanmeta_repo, common.ia_access, common.ia_secret,
        common.ia_collection
    ).process_queue(common.queue, common.timeout)


@click.command()
@common_options
@pass_state
def spacedock_adder(common):
    sd_adder = SpaceDockAdder(
        common.queue,
        common.timeout,
        common.netkan_repo,
        common.github_pr,
    )
    sd_adder.run()
