import unittest
from pathlib import Path, PurePath
from git import Repo

from netkan.common import sqs_batch_entries
from netkan.repos import CkanMetaRepo, NetkanRepo
from netkan.scheduler import NetkanScheduler


class TestScheduler(unittest.TestCase):
    test_data = PurePath(__file__).parent.joinpath('testdata', 'NetKAN')
    ckm_root = PurePath(__file__).parent.joinpath('testdata', 'CKAN-meta')

    def setUp(self):
        self.nk_repo = NetkanRepo(Repo.init(self.test_data))
        self.ckm_repo = CkanMetaRepo(Repo(self.ckm_root))
        self.scheduler = NetkanScheduler(self.nk_repo, self.ckm_repo, 'TestyMcTestFace')
        self.messages = (nk.sqs_message(self.ckm_repo.group(nk.identifier))
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
        test_data = Path(PurePath(__file__).parent, 'testdata/NetTEN')
        scheduler = NetkanScheduler(
            NetkanRepo(Repo.init(test_data)), self.ckm_repo, 'TestyMcTestFace')
        messages = (nk.sqs_message(self.ckm_repo.group(nk.identifier))
                    for nk in scheduler.nk_repo.netkans())

        batches = []
        for batch in sqs_batch_entries(messages):
            batches.append(batch)
        self.assertEqual(len(batches[0]), 10)
        self.assertEqual(len(batches), 1)
