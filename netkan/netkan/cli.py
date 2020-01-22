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
from .mirrorer import Mirrorer


class SharedArgs(object):

    def __init__(self):
        self._environment_data = None
        self._debug = None
        self._ssh_key = None
        self._ckanmeta_remote_repo = None
        self._netkan_remote_repo = None

<<<<<<< HEAD
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
    init_ssh(key, Path(Path.home(), '.ssh'))
    ckan_meta = init_repo(ckanmeta_remote, '/tmp/CKAN-meta')
=======
    def __getattribute__(self, name):
        attr = super().__getattribute__(name)
        if not name.startswith('_') and attr is None:
            logging.fatal("Expecting attribute '%s' to be set; exiting disgracefully!", name)
            sys.exit(1)
        return attr

    @property
    def debug(self):
        return self._debug

    @debug.setter
    def debug(self, value):
        # When there isn't a flag passed we get a None instead, setting
        # it as a 'False' for consistency.
        self._debug = value or False
        # Attempt to set up Discord logger so we can see errors
        if setup_log_handler(self._debug):
            # Catch uncaught exceptions and log them
            sys.excepthook = catch_all

    @property
    def ssh_key(self):
        return self._ssh_key
>>>>>>> Initial CLI Refactor

    @ssh_key.setter
    def ssh_key(self, value):
        init_ssh(value, Path(Path.home(), '.ssh'))
        self._ssh_key = value

    @property
    def ckanmeta_remote(self):
        if not self._ckanmeta_remote_repo:
            self._ckanmeta_remote_repo = init_repo(self._ckanmeta_remote, '/tmp/CKAN-meta')
        return self._ckanmeta_remote_repo

    @ckanmeta_remote.setter
    def ckanmeta_remote(self, value):
        self._ckanmeta_remote = value

    @property
    def netkan_remote(self):
        if not self._netkan_remote_repo:
            self._netkan_remote_repo = init_repo(self._netkan_remote, '/tmp/NetKAN')
        return self._netkan_remote_repo

    @netkan_remote.setter
    def netkan_remote(self, value):
        self._netkan_remote = value

pass_state = click.make_pass_decorator(SharedArgs, ensure=True)


def ctx_callback(ctx, param, value):
    shared = ctx.ensure_object(SharedArgs)
    setattr(shared, param.name, value)
    return value


_common_options = [
    click.option('--debug', is_flag=True, default=False, expose_value=False,
                 help='Enable debug logging', callback=ctx_callback),
    click.option('--queue', envvar='SQS_QUEUE', expose_value=False,
                 help='SQS Queue to poll for metadata', callback=ctx_callback),
    click.option('--ssh-key', envvar='SSH_KEY', expose_value=False,
                 help='SSH key for accessing repositories', callback=ctx_callback),
    click.option('--ckanmeta-remote', envvar='CKANMETA_REMOTE', expose_value=False,
                 help='Path/URL/SSH to Metadata Repo', callback=ctx_callback),
    click.option('--netkan-remote', envvar='NETKAN_REMOTE', expose_value=False,
                 help='Path/URL/SSH to the Stub Metadata Repo', callback=ctx_callback),
    click.option('--token', envvar='GH_Token', expose_value=False,
                 help='GitHub Token for PRs', callback=ctx_callback),
    click.option('--repo', envvar='CKANMETA_REPO', expose_value=False,
                 help='GitHub repo to raise PR against (Org Repo: CKAN-meta)',
                 callback=ctx_callback),
    click.option('--user', envvar='CKANMETA_USER', expose_value=False,
                 help='GitHub user/org repo resides under (Org User: KSP-CKAN)',
                 callback=ctx_callback),
    click.option('--timeout', default=300, envvar='SQS_TIMEOUT', expose_value=False,
                 help='Reduce message visibility timeout for testing', callback=ctx_callback),
    click.option('--dev', is_flag=True, default=False, expose_value=False,
                 help='Disable Production Checks', callback=ctx_callback),
]

def common_options(func):
    for option in reversed(_common_options):
        func = option(func)
    return func


@click.group()
def netkan():
    pass

@click.command()
@common_options
@pass_state
def indexer(common):
    github_pr = GitHubPR(common.token, common.repo, common.user)
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
        with MessageHandler(common.ckanmeta_remote, github_pr) as handler:
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
    '--min-credits', default=200,
    help='Only schedule if we have at least this many credits remaining',
)
@common_options
@pass_state
def scheduler(common, max_queued, group, min_credits):
    sched = NetkanScheduler(
        common.netkan_remote.working_dir, common.ckanmeta_remote.working_dir, common.queue,
        nonhooks_group=(group == 'all' or group == 'nonhooks'),
        webhooks_group=(group == 'all' or group == 'webhooks'),
    )
    if sched.can_schedule(max_queued, common.dev, min_credits):
        sched.schedule_all_netkans()
        logging.info("NetKANs submitted to %s", common.queue)


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
@common_options
@pass_state
def recover_status_timestamps(common):
    ModStatus.recover_timestamps(common.ckanmeta_remote)


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
@common_options
@pass_state
def download_counter(common):
    logging.info('Starting Download Count Calculation...')
    DownloadCounter(
        common.netkan_remote.working_dir,
        common.ckanmeta_remote,
        common.token
    ).update_counts()
    logging.info('Download Counter completed!')


@click.command()
@click.option(
    '--days-limit', default=7,
    help='Number of days to wait for OP to reply',
)
@common_options
@pass_state
def ticket_closer(common, days_limit):
    TicketCloser(common.token).close_tickets(days_limit)


@click.command()
@click.option(
    '--days-limit', default=1000,
    help='Number of days to wait before freezing a mod as idle',
)
<<<<<<< HEAD
@click.option(
    '--key', envvar='SSH_KEY', required=True,
    help='SSH key for accessing repositories',
)
def auto_freezer(netkan_remote, token, repo, user, days_limit, key):
    init_ssh(key, Path(Path.home(), '.ssh'))
    afr = AutoFreezer(
        init_repo(netkan_remote, '/tmp/NetKAN'),
        GitHubPR(token, repo, user)
    )
    afr.freeze_idle_mods(days_limit)
    afr.mark_frozen_mods()


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
    '--ckan-meta', envvar='CKANMETA_REMOTE',
    help='Path/URL/SSH to CKAN-meta repo for mirroring',
    required=True,
)
@click.option(
    '--ia-access', envvar='IA_access',
    help='Credentials for Internet Archive',
    required=True,
)
@click.option(
    '--ia-secret', envvar='IA_secret',
    help='Credentials for Internet Archive',
    required=True,
)
@click.option(
    '--ia-collection', envvar='IA_collection',
    help='Collection to put mirrored mods in on Internet Archive',
    required=True,
)
@click.option(
    '--key', envvar='SSH_KEY', required=True,
    help='SSH key for accessing repositories',
)
def mirrorer(queue, timeout, ckan_meta, ia_access, ia_secret, ia_collection, key):
    init_ssh(key, Path(Path.home(), '.ssh'))
    Mirrorer(
        init_repo(ckan_meta, '/tmp/CKAN-meta'),
        ia_access, ia_secret, ia_collection
    ).process_queue(queue, timeout)


@click.command()
@click.option(
    '--ckan-meta', envvar='CKANMETA_REMOTE',
    help='Path/URL/SSH to CKAN-meta repo for mirroring',
    required=True,
)
@click.option(
    '--ia-access', envvar='IA_access',
    help='Credentials for Internet Archive',
    required=True,
)
@click.option(
    '--ia-secret', envvar='IA_secret',
    help='Credentials for Internet Archive',
    required=True,
)
@click.option(
    '--ia-collection', envvar='IA_collection',
    help='Collection to put mirrored mods in on Internet Archive',
    required=True,
)
@click.option(
    '--dry-run',
    help='',
    default=False,
)
def mirror_purge_epochs(ckan_meta, ia_access, ia_secret, ia_collection, dry_run):
    Mirrorer(
        init_repo(ckan_meta, '/tmp/CKAN-meta'),
        ia_access, ia_secret, ia_collection
    ).purge_epochs(dry_run)


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
    init_ssh(key, Path(Path.home(), '.ssh'))
=======
@common_options
@pass_state
def auto_freezer(common, days_limit):
    afr = AutoFreezer(
        common.netkan_remote,
        GitHubPR(common.token, common.repo, common.user)
    )
    afr.freeze_idle_mods(days_limit)
    afr.mark_frozen_mods()


@click.command()
@common_options
@pass_state
def spacedock_adder(common):
>>>>>>> Initial CLI Refactor
    sd_adder = SpaceDockAdder(
        common.queue,
        common.timeout,
        common.netkan_remote,
        GitHubPR(common.token, common.repo, common.user)
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
netkan.add_command(mirrorer)
netkan.add_command(mirror_purge_epochs)
