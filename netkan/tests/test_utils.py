import unittest
import tempfile
from pathlib import Path
from git import Repo

from netkan.utils import repo_file_add_or_changed


class TestNetKANUtilsRepoFileAddOrChange(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.working = Path(self.tmpdir.name)
        self.repo = Repo.init(self.working)
        Path(self.working, 'existing.txt').touch()
        self.nested = Path(self.working, 'nested')
        self.nested.mkdir()
        Path(self.nested, 'existing_nested.txt').touch()
        self.repo.index.add(self.repo.untracked_files)
        self.repo.index.commit('test')

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_no_file(self):
        no_file = Path(self.working, 'newfile.txt')
        self.assertFalse(repo_file_add_or_changed(self.repo, no_file))

    def test_new_file(self):
        new_file = Path(self.working, 'newfile.txt')
        new_file.touch()
        self.assertTrue(repo_file_add_or_changed(self.repo, new_file))

    def test_no_changes(self):
        existing = Path(self.working, 'existing.txt')
        existing.touch()
        self.assertFalse(repo_file_add_or_changed(self.repo, existing))

    def test_changes(self):
        existing = Path(self.working, 'existing.txt')
        existing.write_text('I made a change', encoding='UTF-8')
        self.assertTrue(repo_file_add_or_changed(self.repo, existing))

    def test_new_nested(self):
        existing = Path(self.nested, 'existing.txt')
        existing.touch()
        self.assertTrue(repo_file_add_or_changed(self.repo, existing))

    def test_changes_nested(self):
        existing = Path(self.nested, 'existing_nested.txt')
        existing.write_text('text', encoding='UTF-8')
        self.assertTrue(repo_file_add_or_changed(self.repo, existing))
