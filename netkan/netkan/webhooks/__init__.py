import os
import boto3
from flask import Flask

from ..utils import init_repo, init_ssh
from ..notifications import setup_log_handler
from .errors import errors
from .inflate import inflate
from .spacedock_inflate import spacedock_inflate
from .github_inflate import github_inflate


def create_app():
    # Set up Discord logger so we can see errors
    setup_log_handler()

    app = Flask(__name__)

    init_ssh(os.environ.get('SSH_KEY'), '/home/netkan/.ssh')

    # Set up config
    app.config['secret'] = os.environ.get('XKAN_GHSECRET')
    app.config['netkan_repo'] = init_repo(os.environ.get('NETKAN_REMOTE'), '/tmp/NetKAN')
    app.config['ckanmeta_repo'] = init_repo(os.environ.get('CKANMETA_REMOTE'), '/tmp/CKAN-meta')
    app.config['repos'] = [app.config['netkan_repo'], app.config['ckanmeta_repo']]
    app.config['client'] = boto3.client('sqs')
    sqs = boto3.resource('sqs')
    app.config['inflation_queue'] = sqs.get_queue_by_name(
        QueueName=os.environ.get('INFLATION_SQS_QUEUE'))

    # Add the hook handlers
    app.register_blueprint(errors)
    app.register_blueprint(inflate)
    app.register_blueprint(spacedock_inflate, url_prefix='/sd')
    app.register_blueprint(github_inflate, url_prefix='/gh')

    return app
