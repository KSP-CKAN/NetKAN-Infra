from pathlib import Path, PurePath

from netkan.common import sqs_batch_entries
from netkan.scheduler import NetkanScheduler

from .common import SharedArgsHarness


class TestScheduler(SharedArgsHarness):
    repos = ['ckan', 'netkan', 'countkan']
    netkan_data = Path(PurePath(__file__).parent, 'testdata', 'NetKAN')
    ckan_data = Path(PurePath(__file__).parent, 'testdata', 'CKAN-meta')
    countkan_data = Path(PurePath(__file__).parent, 'testdata', 'NetTEN')

    def setUp(self):
        super().setUp()
        self.scheduler = NetkanScheduler(
            self.shared_args, 'TestyMcTestFace', 'token', 'ksp')
        self.messages = (nk.sqs_message(self.scheduler.ckm_repo.highest_version(nk.identifier))
                         for nk in self.scheduler.nk_repo.netkans())

    def test_netkans(self):
        self.assertEqual(
            len(list(self.scheduler.nk_repo.netkans())), 13
        )

    def test_sqs_batching(self):
        batches = []
        for batch in sqs_batch_entries(self.messages):
            batches.append(batch)
        self.assertEqual(len(batches[0]), 10)
        self.assertEqual(len(batches[1]), 3)

    def test_sqs_batch_attrs(self):
        batch = list(sqs_batch_entries(self.messages))[0]
        attrs = self.scheduler.sqs_batch_attrs(batch)
        self.assertEqual(attrs['QueueUrl'], 'test_url')
        self.assertEqual(len(attrs['Entries']), 10)

    def test_sqs_batching_ten(self):
        setattr(self.shared_args, 'netkan_remotes',
                (f'count={getattr(self, "countkan_upstream")}',))
        setattr(self.shared_args, 'ckanmeta_remotes',
                (f'count={getattr(self, "ckan_upstream")}',))
        scheduler = NetkanScheduler(
            self.shared_args, 'TestyMcTestFace', 'token', 'count')
        messages = (nk.sqs_message(scheduler.ckm_repo.highest_version(nk.identifier))
                    for nk in scheduler.nk_repo.netkans())

        batches = []
        for batch in sqs_batch_entries(messages):
            batches.append(batch)
        self.assertEqual(len(batches[0]), 10)
        self.assertEqual(len(batches), 1)
