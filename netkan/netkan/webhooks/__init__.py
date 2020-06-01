import os
import sys
import boto3
from flask import Flask
from pathlib import Path

from ..utils import init_repo, init_ssh
from ..notifications import setup_log_handler, catch_all
from ..repos import NetkanRepo, CkanMetaRepo
from .errors import errors
from .inflate import inflate
from .spacedock_inflate import spacedock_inflate
from .spacedock_add import spacedock_add
from .github_inflate import github_inflate
from .github_mirror import github_mirror


def create_app() -> Flask:
    # Set up Discord logger so we can see errors
    if setup_log_handler():
        sys.excepthook = catch_all

    app = Flask(__name__)

    init_ssh(os.environ.get('SSH_KEY', ''), Path(Path.home(), '.ssh'))

    # Set up config
    app.config['secret'] = os.environ.get('XKAN_GHSECRET')
    app.config['nk_repo'] = NetkanRepo(
        init_repo(os.environ.get('NETKAN_REMOTE', ''), '/tmp/NetKAN', False))
    app.config['ckm_repo'] = CkanMetaRepo(
        init_repo(os.environ.get('CKANMETA_REMOTE', ''), '/tmp/CKAN-meta', False))
    app.config['repos'] = [app.config['nk_repo'].git_repo, app.config['ckm_repo'].git_repo]
    app.config['client'] = boto3.client('sqs')
    sqs = boto3.resource('sqs')
    app.config['inflation_queue'] = sqs.get_queue_by_name(
        QueueName=os.environ.get('INFLATION_SQS_QUEUE'))
    app.config['add_queue'] = sqs.get_queue_by_name(QueueName=os.environ.get('ADD_SQS_QUEUE'))
    app.config['mirror_queue'] = sqs.get_queue_by_name(QueueName=os.environ.get('MIRROR_SQS_QUEUE'))

    # Add the hook handlers
    app.register_blueprint(errors)
    app.register_blueprint(inflate)
    app.register_blueprint(spacedock_inflate, url_prefix='/sd')
    app.register_blueprint(spacedock_add, url_prefix='/sd')
    app.register_blueprint(github_inflate, url_prefix='/gh')
    app.register_blueprint(github_mirror, url_prefix='/gh')

    return app
