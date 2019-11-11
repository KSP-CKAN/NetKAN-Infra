import datetime
import logging
from pathlib import Path
import boto3
import requests

from .metadata import Netkan
from .common import sqs_batch_entries


class NetkanScheduler:

    def __init__(self, path, queue, base='NetKAN/', nonhooks_group=False, webhooks_group=False):
        self.path = Path(path, base)
        self.nonhooks_group = nonhooks_group
        self.webhooks_group = webhooks_group

        # TODO: This isn't super neat, do something better.
        self.queue_url = 'test_url'
        if queue != 'TestyMcTestFace':
            self.client = boto3.client('sqs')
            sqs = boto3.resource('sqs')
            self.queue = sqs.get_queue_by_name(QueueName=queue)
            self.queue_url = self.queue.url

    def netkans(self):
        # This can easily be recursive with '**/*.netkan', however
        # implementing like for like initially.
        return (Netkan(f) for f in self.path.glob('*.netkan'))

    def sqs_batch_attrs(self, batch):
        return {
            'QueueUrl': self.queue_url,
            'Entries': batch
        }

    def _in_group(self, netkan):
        if netkan.hook_only():
            return self.webhooks_group
        else:
            return self.nonhooks_group

    def schedule_all_netkans(self):
        messages = (nk.sqs_message() for nk in self.netkans() if self._in_group(nk))
        for batch in sqs_batch_entries(messages):
            self.client.send_message_batch(**self.sqs_batch_attrs(batch))

    def can_schedule(self, max_queued, dev=False, min_credits=200):
        if not dev:
            end = datetime.datetime.utcnow()
            start = end - datetime.timedelta(minutes=10)
            response = requests.get(
                'http://169.254.169.254/latest/meta-data/instance-id'
            )
            instance_id = response.text
            cloudwatch = boto3.client('cloudwatch')
            stats = cloudwatch.get_metric_statistics(
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                MetricName='CPUCreditBalance',
                Namespace='AWS/EC2',
                StartTime=start.strftime("%Y-%m-%dT%H:%MZ"),
                EndTime=end.strftime("%Y-%m-%dT%H:%MZ"),
                Period=10,
                Statistics=['Average'],
            )
            # A pass consumes around 40 credits, with an accrue rate of 24/hr.
            # So running every 2 hours should see using just a touch less than
            # we gain in that time period.
            creds = 0
            try:
                creds = stats['Datapoints'][0]['Average']
            except IndexError:
                logging.error("Couldn't acquire CPU Credit Stats")
            if int(creds) < min_credits:
                logging.info(
                    "Run skipped, below credit target (Current Avg: %s)", creds
                )
                return False

        message_count = int(
            self.queue.attributes.get(
                'ApproximateNumberOfMessages', 0)
        )
        if message_count > max_queued:
            logging.info(
                "Run skipped, too many NetKANs to process (%s left)",
                message_count
            )
            return False

        return True
