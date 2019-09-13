import boto3
import datetime
import logging
import requests
from pathlib import Path
from hashlib import md5


class NetkanScheduler:

    def __init__(self, path, queue, base='NetKAN/'):
        self.path = Path(path, base)

        # TODO: This isn't super neat, do something better.
        self.queue_url = 'test_url'
        if queue != 'TestyMcTestFace':
            self.client = boto3.client('sqs')
            sqs = boto3.resource('sqs')
            self.queue = sqs.get_queue_by_name(QueueName=queue)
            self.queue_url = self.queue.url

    def netkans(self):
        # This can easily be recursive with '**/*.netkan', however
        # implemeneting like for like initially.
        return self.path.glob('*.netkan')

    def generate_netkan_message(self, filename):
        content = Path(filename).read_text()
        return {
            'Id': filename.stem,
            'MessageBody': content,
            'MessageGroupId': '1',
            'MessageDeduplicationId': md5(content.encode()).hexdigest()
        }

    def sqs_batch_entries(self, batch_size=10):
        batch = []

        for netkan in self.netkans():
            batch.append(self.generate_netkan_message(netkan))
            if len(batch) == batch_size:
                yield(batch)
                batch = []
        yield(batch)

    def sqs_batch_attrs(self, batch):
        return {
            'QueueUrl': self.queue_url,
            'Entries': batch
        }

    def schedule_all_netkans(self):
        for batch in self.sqs_batch_entries():
            self.client.send_message_batch(**self.sqs_batch_attrs(batch))

    def can_schedule(self, max_queued, dev=False):
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
            credits = 0
            try:
                credits = stats['Datapoints'][0]['Average']
            except IndexError:
                logging.error("Couldn't acquire CPU Credit Stats")
            if int(credits) < 250:
                logging.info(
                    "Run skipped, below credit target (Current Avg: {})".format(
                        credits
                    )
                )
                return False

        message_count = int(
            self.queue.attributes.get(
                'ApproximateNumberOfMessages', 0)
        )
        if message_count > max_queued:
            logging.info(
                "Run skipped, too many NetKANs to process ({} left)".format(
                    message_count
                )
            )
            return False

        return True
