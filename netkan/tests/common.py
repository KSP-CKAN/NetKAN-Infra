import shutil
import tempfile

from unittest import TestCase, mock
from pathlib import Path, PurePath

from git import Repo
from gitdb.exc import BadName

from netkan.cli.common import SharedArgs


class SharedArgsHarness(TestCase):
    repos = ['ckan', 'netkan']
    ckan_data = Path(PurePath(__file__).parent, 'testdata/CKAN-meta')
    netkan_data = Path(PurePath(__file__).parent, 'testdata/NetKAN')
    tmpdir: tempfile.TemporaryDirectory

    @classmethod
    def setUpClass(cls):
        super(SharedArgsHarness, cls).setUpClass()
        cls.tmpdir = tempfile.TemporaryDirectory()
        for repo in cls.repos:
            working = Path(cls.tmpdir.name, 'working', repo)
            upstream = Path(cls.tmpdir.name, 'upstream', repo)
            upstream.mkdir(parents=True)
            Repo.init(upstream, bare=True)
            shutil.copytree(getattr(cls, f'{repo}_data'), working)
            git_repo = Repo.init(working)
            shutil.copy(Path(__file__).parent.parent / '.gitconfig',
                        working / '.git' / 'config')
            git_repo.index.add(git_repo.untracked_files)
            git_repo.index.commit('Test Data')
            git_repo.create_remote('origin', upstream.as_posix())
            git_repo.remotes.origin.push('master:master')
            setattr(cls, f'{repo}_path', working)
            setattr(cls, f'{repo}_upstream', upstream)

    @classmethod
    def tearDownClass(cls):
        super(SharedArgsHarness, cls).tearDownClass()
        cls.tmpdir.cleanup()

    def setUp(self):
        patch = mock.patch(
            'netkan.cli.common.Game.clone_base', self.tmpdir.name)
        patch.start()
        self.shared_args = SharedArgs()
        self.shared_args.deep_clone = True
        self.shared_args.token = '1234'
        self.shared_args.user = 'ckan-test'
        ckan_upstream = getattr(self, 'ckan_upstream')
        netkan_upstream = getattr(self, 'netkan_upstream')
        attributes = [
            ('ckanmeta_remote',
             (f'ksp={ckan_upstream}', f'ksp2={ckan_upstream}')),
            ('netkan_remote',
             (f'ksp={netkan_upstream}', f'ksp2={netkan_upstream}')),
            ('repo',
             ('ksp=Test/KSP', 'ksp2=Test/KSP2')),
        ]
        for attr, val in attributes:
            setattr(self.shared_args, attr, val)

    def tearDown(self):
        for repo in ['ckan_path', 'netkan_path']:
            meta = Repo(getattr(self, repo))
            meta.git.clean('-df')
            meta.heads.master.checkout()
            try:
                cleanup = meta.create_head('cleanup', 'HEAD~1')
                meta.head.reference = cleanup
                meta.head.reset(index=True, working_tree=True)
            except BadName:
                pass
        mock.patch.stopall()

    @staticmethod
    def mocked_message(staged=False):
        msg = mock.Mock()
        msg.body = Path(
            PurePath(__file__).parent,
            'testdata/DogeCoinFlag-v1.02.ckan'
        ).read_text('utf-8')
        msg.message_attributes = {
            'CheckTime': {
                'StringValue': '2019-06-24T19:06:14', 'DataType': 'String'},
            'ModIdentifier': {
                'StringValue': 'DogeCoinFlag', 'DataType': 'String'},
            'Staged': {'StringValue': str(staged), 'DataType': 'String'},
            'Success': {'StringValue': 'True', 'DataType': 'String'},
            'FileName': {
                'StringValue': './DogeCoinFlag-v1.02.ckan',
                'DataType': 'String'
            }
        }
        msg.message_id = 'MessageMcMessageFace'
        msg.receipt_handle = 'HandleMcHandleFace'
        msg.md5_of_body = '709d9d3484f8c1c719b15a8c3425276a'
        return msg
