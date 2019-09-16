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

    def __list_split(self, list, length):
        return (list[n:(n+length)] for n in range(0, len(list), length))

    def sqs_batch_entries(self, batch_size=10):
        for batch in self.__list_split(self.netkans(), batch_size):
            yield [self.generate_netkan_message(nk) for nk in batch]

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
            # TODO: Make this a cli option. The amount of times I've changed it! My
            #       current thinking is we should calculate how many credits we use
            #       per run vs how many we accrue and schedule with a frequency just
            #       a little less as to always be giving us headroom. Currently it's
            #       around 40 credits, with an accrue rate of 24/hr. So running every
            #       2 hours should see using just a touch less than we gain in that
            #       time period.
            credits = 0
            try:
                credits = stats['Datapoints'][0]['Average']
            except IndexError:
                logging.error("Couldn't acquire CPU Credit Stats")
            if int(credits) < 100:
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
