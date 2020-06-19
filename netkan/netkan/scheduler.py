import datetime
import logging
from typing import List, Dict, Any

import boto3
import requests

from .repos import NetkanRepo, CkanMetaRepo
from .metadata import Netkan
from .common import sqs_batch_entries, github_limit_remaining


class NetkanScheduler:

    def __init__(self, nk_repo: NetkanRepo, ckm_repo: CkanMetaRepo, queue: str, github_token: str,
                 nonhooks_group: bool = False, webhooks_group: bool = False) -> None:
        self.nk_repo = nk_repo
        self.ckm_repo = ckm_repo
        self.nonhooks_group = nonhooks_group
        self.webhooks_group = webhooks_group
        self.github_token = github_token

        # TODO: This isn't super neat, do something better.
        self.queue_url = 'test_url'
        if queue != 'TestyMcTestFace':
            self.client = boto3.client('sqs')
            sqs = boto3.resource('sqs')
            self.queue = sqs.get_queue_by_name(QueueName=queue)
            self.queue_url = self.queue.url

    def sqs_batch_attrs(self, batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            'QueueUrl': self.queue_url,
            'Entries': batch
        }

    def _in_group(self, netkan: Netkan) -> bool:
        if netkan.hook_only():
            return self.webhooks_group
        else:
            return self.nonhooks_group

    def schedule_all_netkans(self) -> None:
        messages = (nk.sqs_message(self.ckm_repo.highest_version(nk.identifier))
                    for nk in self.nk_repo.netkans() if self._in_group(nk))
        for batch in sqs_batch_entries(messages):
            self.client.send_message_batch(**self.sqs_batch_attrs(batch))

    def cpu_credits(self, cloudwatch: 'boto3.CloudWatch.Client', instance_id: str, start: datetime.datetime, end: datetime.datetime) -> int:
        stats = cloudwatch.get_metric_statistics(
            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
            MetricName='CPUCreditBalance',
            Namespace='AWS/EC2',
            StartTime=start.strftime("%Y-%m-%dT%H:%MZ"),
            EndTime=end.strftime("%Y-%m-%dT%H:%MZ"),
            Period=10,
            Statistics=['Average'],
        )
        # An initial pass after redeployment of the inflator consumes around 15 credits
        # and followup passes around 5, with an accrue rate of 24/hr. This is a historical
        # check, but useful to avoid DoS'ing the service when we're doing high CPU operations.
        creds = 0
        try:
            creds = stats['Datapoints'][0]['Average']
        except IndexError:
            logging.error("Couldn't acquire CPU Credit Stats")
        return int(creds)

    def volume_credits_percent(self, cloudwatch: 'boto3.CloudWatch.Client', instance_id: str, start: datetime.datetime, end: datetime.datetime) -> int:
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
            Dimensions=[{'Name': 'VolumeId', 'Value': volume_id}],
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

    def can_schedule(self, max_queued: int, dev: bool = False,
                     min_cpu: int = 50, min_io: int = 70, min_gh: int = 1500) -> bool:
        if not dev:
            github_remaining = github_limit_remaining(self.github_token)
            if github_remaining < min_gh:
                logging.error(
                    "Run skipped, GitHub API limit nearing exhaustion (Current: %s)",
                    github_remaining
                )
                return False

            end = datetime.datetime.utcnow()
            start = end - datetime.timedelta(minutes=10)
            response = requests.get(
                'http://169.254.169.254/latest/meta-data/instance-id'
            )
            instance_id = response.text
            cloudwatch = boto3.client('cloudwatch')

            # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-monitoring-cpu-credits.html
            cpu_credits = self.cpu_credits(cloudwatch, instance_id, start, end)
            if cpu_credits < min_cpu:
                logging.info(
                    "Run skipped, below cpu credit target (Current Avg: %s)", cpu_credits
                )
                return False

            # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ebs-volume-types.html
            # Volume Burst balance measured in a percentage of 5.4million credits. Credits are
            # accrued at a rate of 3 per GB, per second. If we are are down to min_io percent of
            # our max, something has likely gone wrong and we should not queue any more
            # inflations. A regular run seems to consume between 10-15%
            vol_credits_percent = self.volume_credits_percent(cloudwatch, instance_id, start, end)
            if vol_credits_percent < min_io:
                logging.error(
                    "Run skipped, below volume credit target percentage (Current Avg: %s)",
                    vol_credits_percent
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
