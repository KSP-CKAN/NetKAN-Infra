import os
import sys
from flask import Flask

from ..notifications import setup_log_handler, catch_all
from .config import current_config
from .errors import errors
from .inflate import inflate
from .spacedock_inflate import spacedock_inflate
from .spacedock_add import spacedock_add
from .github_inflate import github_inflate
from .github_mirror import github_mirror


class NetkanWebhooks(Flask):

    def __init__(self) -> None:
        super().__init__(__name__)

        # Set up Discord logger so we can see errors
        if setup_log_handler():
            sys.excepthook = catch_all

        # Add the hook handlers
        self.register_blueprint(errors)
        self.register_blueprint(inflate)
        self.register_blueprint(spacedock_inflate, url_prefix='/sd')
        self.register_blueprint(spacedock_add, url_prefix='/sd')
        self.register_blueprint(github_inflate, url_prefix='/gh')
        self.register_blueprint(github_mirror, url_prefix='/gh')


def create_app() -> NetkanWebhooks:
    # Set config values for other modules to retrieve
    current_config.setup(
        ssh_key=os.environ.get('SSH_KEY', ''),
        secret=os.environ.get('XKAN_GHSECRET', ''),
        netkan_remote=os.environ.get('NETKAN_REMOTES', ''),
        ckanmeta_remote=os.environ.get('CKANMETA_REMOTES', ''),
        inf_queue_name=os.environ.get('INFLATION_SQS_QUEUES', ''),
        add_queue_name=os.environ.get('ADD_SQS_QUEUE', ''),
        mir_queue_name=os.environ.get('MIRROR_SQS_QUEUE', '')
    )
    return NetkanWebhooks()
