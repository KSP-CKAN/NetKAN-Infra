import boto3
import json
import hashlib
from pathlib import Path, PurePath
from git import Repo
from collections import deque

class CkanMessage:

    def __init__(self, msg, meta_path):
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
        self.meta_path = meta_path

    def __str__(self):
        return '{}: {}'.format(self.ModIdentifier, self.CheckTime)

    @property
    def stored_file(self):
        return Path(self.meta_path, self.ModIdentifier, self.FileName)

    def metadata_changed(self):
        md5 = hashlib.md5(self.stored_file.read_bytes()).hexdigest()
        if md5 == self.md5_of_body:
            return True
        return False

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
