from pathlib import Path
from hashlib import md5


class NetkanScheduler:

    def __init__(self, path, queue_url, client, base='NetKAN/'):
        self.path = Path(path, base)
        self.queue_url = queue_url
        self.client = client

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
