import datetime
import logging
from pathlib import Path
import boto3
import requests

from .metadata import Netkan, CkanGroup
from .common import sqs_batch_entries


class NetkanScheduler:

    def __init__(self, path, ckan_meta_path, queue,
                 base='NetKAN/', nonhooks_group=False, webhooks_group=False):
        self.path = Path(path, base)
        self.nonhooks_group = nonhooks_group
        self.webhooks_group = webhooks_group
        self.ckan_meta_path = ckan_meta_path

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
        return (Netkan(f) for f in sorted(self.path.glob('*.netkan'),
                                          key=lambda p: p.stem.casefold()))

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
        messages = (nk.sqs_message(CkanGroup(self.ckan_meta_path, nk.identifier))
                    for nk in self.netkans() if self._in_group(nk))
        for batch in sqs_batch_entries(messages):
            self.client.send_message_batch(**self.sqs_batch_attrs(batch))

    def cpu_credits(self, cloudwatch, instance_id, start, end):
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
        return int(creds)

    def volume_credits(self, cloudwatch, instance_id, start, end):
        client = boto3.client('ec2')
        response = client.describe_volumes(
            Filters=[{
                'Name': 'attachment.instance-id',
                'Values': [instance_id]
            }]
        )
        # If we add a second gp2 volume, this may break
        volume = list(filter(lambda x: x['VolumeType'] == 'gp2', response['Volumes']))[0]
        volume_id = volume['Attachments'][0]['VolumeId']
        stats = cloudwatch.get_metric_statistics(
            Dimensions=[{'Name': 'VolumeId', 'Value': 'vol-02cdb3dfd4b2a69f9'}],
            MetricName='BurstBalance',
            Namespace='AWS/EBS',
            StartTime=start.strftime("%Y-%m-%dT%H:%MZ"),
            EndTime=end.strftime("%Y-%m-%dT%H:%MZ"),
            Period=10, Statistics=['Average'],
        )
        creds = 0
        try:
            creds = stats['Datapoints'][0]['Average']
        except IndexError:
            logging.error("Couldn't acquire Volume Credit Stats")
        return int(creds)

    def can_schedule(self, max_queued, dev=False, min_credits=200):
        if not dev:
            end = datetime.datetime.utcnow()
            start = end - datetime.timedelta(minutes=10)
            response = requests.get(
                'http://169.254.169.254/latest/meta-data/instance-id'
            )
            instance_id = response.text
            cloudwatch = boto3.client('cloudwatch')

            cpu_credits = self.cpu_credits(cloudwatch, instance_id, start, end)
            if cpu_credits < min_credits:
                logging.info(
                    "Run skipped, below cpu credit target (Current Avg: %s)", cpu_credits
                )
                return False

            # Volume Burst balance measured in a percentage of 5.4million credits. Credits are
            # accrued at a rate of 3 per GB, per second. If we are are down to 30 percent of
            # our max, something has gone wrong and we should not queue any more inflations.
            vol_credits = self.volume_credits(cloudwatch, instance_id, start, end)
            if vol_credits < 30:
                logging.info(
                    "Run skipped, below volume credit target (Current Avg: %s %)", vol_credits
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
