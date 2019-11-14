import logging
import time
import click

from ..status import ModStatus


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
