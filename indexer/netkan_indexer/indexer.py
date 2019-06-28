import boto3
import json
import hashlib
from pathlib import Path, PurePath
from collections import deque

class CkanMessage:

    def __init__(self, msg, ckan_meta):
        self.body = msg.body
        for item in msg.message_attributes.items():
            attr_type = '{}Value'.format(item[1]['DataType'])
            content = item[1][attr_type]
            if content.lower() in ['true','false']:
                content = True if content.lower() == 'true' else False
            if item[0] == 'FileName':
                content = PurePath(content).name
            setattr(self, item[0], content)
        self.md5_of_body = msg.md5_of_body
        self.message_id = msg.message_id
        self.receipt_handle = msg.receipt_handle
        self.ckan_meta = ckan_meta

    def __str__(self):
        return '{}: {}'.format(self.ModIdentifier, self.CheckTime)

    @property
    def mod_path(self):
        return Path(self.ckan_meta.working_dir, self.ModIdentifier)

    @property
    def mod_file(self):
        return Path(self.mod_path, self.FileName)

    def mod_file_md5(self):
        with open(self.mod_file, mode='rb') as f:
            return hashlib.md5(f.read()).hexdigest()

    def metadata_changed(self):
        if not self.mod_file.exists():
            return True
        if self.mod_file_md5() == self.md5_of_body:
            return False
        return True

    def write_metadata(self):
        self.mod_path.mkdir(exist_ok=True)
        with open(self.mod_file, mode='w') as f:
            f.write(self.body)

    def commit_metadata(self):
        index = self.ckan_meta.index
        index.add(self.ckan_meta.untracked_files)
        return index.commit('NetKAN generated mods - {}'.format(self.mod_file.stem))

    @property
    def delete_attrs(self):
        return { 'Id': self.message_id, 'ReceiptHandle': self.receipt_handle }


class MessageHandler:

    def __init__(self, repo):
        self.repo = repo
        self.master = deque()
        self.staged = deque()
        self.processed = []

    def add(self, ckan):
        if not ckan.staged:
            self.master.append(ckan)
        else:
            self.staged.append(ckan)

    def __str__(self):
        return str(self.master) + str(self.staged)

    # Apparently gitpython can be leaky on long running processes
    # we can ensure we call close on it and run our handler inside
    # a context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # call git repo close action
        pass