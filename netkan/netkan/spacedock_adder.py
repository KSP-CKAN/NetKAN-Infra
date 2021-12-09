import json
import re
import io
from importlib.resources import read_text
from string import Template
from collections import defaultdict
import logging
from typing import Dict, Any, Optional
import git
import boto3
from ruamel.yaml import YAML

from .github_pr import GitHubPR
from .mod_analyzer import ModAnalyzer
from .common import deletion_msg

from .repos import NetkanRepo


# https://github.com/KSP-SpaceDock/SpaceDock/blob/master/KerbalStuff/ckan.py
class SpaceDockAdder:

    PR_BODY_TEMPLATE = Template(read_text('netkan', 'pr_body_template.md'))

    def __init__(self, queue: str, timeout: int, nk_repo: NetkanRepo, github_pr: GitHubPR = None) -> None:
        sqs = boto3.resource('sqs')
        self.sqs_client = boto3.client('sqs')
        self.queue = sqs.get_queue_by_name(QueueName=queue)
        self.timeout = timeout
        self.nk_repo = nk_repo
        self.github_pr = github_pr
        self.yaml = YAML()
        self.yaml.indent(mapping=2, sequence=4, offset=2)

    def run(self) -> None:
        while True:
            messages = self.queue.receive_messages(
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All'],
                VisibilityTimeout=self.timeout,
            )
            if messages:
                self.nk_repo.git_repo.heads.master.checkout()
                self.nk_repo.git_repo.remotes.origin.pull('master', strategy_option='ours')

                # Start processing the messages
                to_delete = []
                for msg in messages:
                    if self.try_add(json.loads(msg.body)):
                        # Successfully handled -> OK to delete
                        to_delete.append(deletion_msg(msg))
                self.queue.delete_messages(Entries=to_delete)
                # Clean up GitPython's lingering file handles between batches
                self.nk_repo.git_repo.close()

    def try_add(self, info: Dict[str, Any]) -> bool:
        netkan = self.make_netkan(info)

        # Create .netkan file or quit if already there
        netkan_path = self.nk_repo.nk_path(netkan.get('identifier', ''))
        if netkan_path.exists():
            # Already exists, we are done
            return True

        # Create branch
        branch_name = f"add/{netkan.get('identifier')}"
        try:
            self.nk_repo.git_repo.remotes.origin.fetch(branch_name)
        except git.GitCommandError:
            # *Shrug*
            pass
        if branch_name not in self.nk_repo.git_repo.heads:
            self.nk_repo.git_repo.create_head(
                branch_name,
                getattr(
                    self.nk_repo.git_repo.remotes.origin.refs,
                    branch_name,
                    self.nk_repo.git_repo.remotes.origin.refs.master
                )
            )
        # Checkout branch
        self.nk_repo.git_repo.heads[branch_name].checkout()

        # Create file
        netkan_path.write_text(self.yaml_dump(netkan))

        # Add netkan to branch
        self.nk_repo.git_repo.index.add([netkan_path.as_posix()])

        # Commit
        self.nk_repo.git_repo.index.commit(
            (
                f"Add {info.get('name')} from {info.get('site_name')}"
                f"\n\nThis is an automated commit on behalf of {info.get('username')}"
            ),
            author=git.Actor(info.get('username'), info.get('email'))
        )

        # Push branch
        self.nk_repo.git_repo.remotes.origin.push('{mod}:{mod}'.format(mod=branch_name))

        # Create pull request
        if self.github_pr:
            self.github_pr.create_pull_request(
                title=f"Add {info.get('name')} from {info.get('site_name')}",
                branch=branch_name,
                body=self.PR_BODY_TEMPLATE.safe_substitute(defaultdict(lambda: '', info)),
                labels=['Pull request', 'Mod-request'],
            )
        return True

    def yaml_dump(self, obj: Dict[str, Any]) -> str:
        sio = io.StringIO()
        self.yaml.dump(obj, sio)
        return sio.getvalue()

    @staticmethod
    def sd_download_url(info: Dict[str, Any]) -> str:
        return f"https://spacedock.info/mod/{info.get('id', '')}/{info.get('name', '')}/download"

    @classmethod
    def make_netkan(cls, info: Dict[str, Any]) -> Dict[str, Any]:
        ident = re.sub(r'\W+', '', info.get('name', ''))
        mod: Optional[ModAnalyzer] = None
        url = SpaceDockAdder.sd_download_url(info)
        try:
            mod = ModAnalyzer(ident, url)
        except Exception as exc:  # pylint: disable=broad-except
            # Tell Discord about the problem and move on
            logging.error('%s failed to analyze %s from %s',
                cls.__name__, ident, url, exc_info=exc)
        return {
            'spec_version': 'v1.4',
            'identifier': ident,
            '$kref': f"#/ckan/spacedock/{info.get('id', '')}",
            'license': info.get('license', '').strip().replace(' ', '-'),
            **(mod.get_netkan_properties() if mod else {}),
            'x_via': f"Automated {info.get('site_name')} CKAN submission"
        }
