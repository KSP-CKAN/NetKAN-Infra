import boto3
import json
from gitpython import Repo
from pathlib import Path
from collections import deque

class CkanMessage:

    def __init__(self, msg):
        self.msg = msg
        for attr in msg.msg.message_attributes:
            content = msg.message_attributes[attr]
            if content.lower() in ['true','false']:
                content = True if attr == 'true' else False
            setattr(self, attr, msg.message_attributes[attr])
        self.id = msg['MessageId']
        self.receipt_handle = msg['ReceiptHandle']

    def __str__(self):
        return self.ModIdentifier

    @property
    def body(self):
        return self.msg.body

    @property
    def delete_attrs(self):
        return { 'Id': self.id, 'ReceiptHandle': self.receipt_handle }

class MessageHandler:

    def __init__(self, repo)
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
        return self.master + self.staged

    # Apparently gitpython can be leaky on long running processes
    # we can ensure we call close on it and run our handler inside
    # a context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # call git repo close action
        pass
