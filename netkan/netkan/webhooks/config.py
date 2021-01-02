from pathlib import Path
import boto3

from ..repos import NetkanRepo, CkanMetaRepo
from ..utils import init_repo, init_ssh


class WebhooksConfig:

    # Ideally this would be __init__, but we want other modules to
    # import a reference to our global config object before we set
    # its properties, and that requires a temporary 'empty' state.
    def setup(self, ssh_key: str, secret: str,
              netkan_remote: str, netkan_path: str,
              ckanmeta_remote: str, ckanmeta_path: str,
              inf_queue_name: str, add_queue_name: str, mir_queue_name: str) -> None:

        self.secret = secret
        # Cloning the repos requires an SSH key set up in our home dir
        init_ssh(ssh_key, Path(Path.home(), '.ssh'))

        self.nk_repo = NetkanRepo(init_repo(netkan_remote, netkan_path, False))
        self.ckm_repo = CkanMetaRepo(init_repo(ckanmeta_remote, ckanmeta_path, False))
        self.repos = [self.nk_repo.git_repo, self.ckm_repo.git_repo]

        if inf_queue_name or add_queue_name or mir_queue_name:
            self.client = boto3.client('sqs')
            sqs = boto3.resource('sqs')
            self.inflation_queue = sqs.get_queue_by_name(QueueName=inf_queue_name)
            self.add_queue = sqs.get_queue_by_name(QueueName=add_queue_name)
            self.mirror_queue = sqs.get_queue_by_name(QueueName=mir_queue_name)


# Provide the active config to other modules
current_config = WebhooksConfig()
