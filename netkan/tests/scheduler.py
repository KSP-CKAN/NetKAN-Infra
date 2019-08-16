from netkan.scheduler import NetkanScheduler

import unittest
from pathlib import Path, PurePath


class TestNetKAN(unittest.TestCase):
    test_data = Path(PurePath(__file__).parent, 'testdata/NetKAN')

    def setUp(self):
        self.scheduler = NetkanScheduler(self.test_data, 'test_url', 'client')

    def test_netkan_message(self):
        dogecoinflag = Path(self.test_data, 'NetKAN/DogeCoinFlag.netkan')
        message = self.scheduler.generate_netkan_message(dogecoinflag)
        self.assertEqual(message['Id'], 'DogeCoinFlag')
        self.assertEqual(
            message['MessageBody'],
            dogecoinflag.read_text()
        )
        self.assertEqual(message['MessageGroupId'], '1')
        self.assertEqual(
            message['MessageDeduplicationId'],
            '9de6d1d75799b42a7fd754073613942f'
        )

    def test_netkans(self):
        self.assertEqual(
            len(list(self.scheduler.netkans())), 11
        )

    def test_sqs_batching(self):
        batches = []
        for batch in self.scheduler.sqs_batch_entries():
            batches.append(batch)
        self.assertEqual(len(batches[0]), 10)
        self.assertEqual(len(batches[1]), 1)

    def test_sqs_batch_attrs(self):
        batch = list(self.scheduler.sqs_batch_entries())[0]
        attrs = self.scheduler.sqs_batch_attrs(batch)
        self.assertEqual(attrs['QueueUrl'], 'test_url')
        self.assertEqual(len(attrs['Entries']), 10)
