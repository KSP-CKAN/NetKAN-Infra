import json
import re
from pathlib import Path
from importlib.resources import read_text
from string import Template
import git
import boto3


# https://github.com/KSP-SpaceDock/SpaceDock/blob/master/KerbalStuff/ckan.py
class SpaceDockAdder:

    PR_BODY_TEMPLATE = Template(read_text('netkan', 'pr_body_template.txt'))

    def __init__(self, queue, timeout, netkan_repo, github_pr):
        sqs = boto3.resource('sqs')
        self.sqs_client = boto3.client('sqs')
        self.queue = sqs.get_queue_by_name(QueueName=queue)
        self.timeout = timeout
        self.netkan_repo = netkan_repo
        self.github_pr = github_pr

    def run(self):
        while True:
            messages = self.queue.receive_messages(
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All'],
                VisibilityTimeout=self.timeout,
            )
            if messages:
                self.netkan_repo.heads.master.checkout()
                self.netkan_repo.remotes.origin.pull('master', strategy_option='ours')

                # Start processing the messages
                to_delete = []
                for msg in messages:
                    if self.try_add(json.loads(msg.body)):
                        # Successfully handled -> OK to delete
                        to_delete.append(self.deletion_msg(msg))
                self.queue.delete_messages(Entries=to_delete)
                # Clean up GitPython's lingering file handles between batches
                self.netkan_repo.close()

    def try_add(self, info):
        netkan = self.make_netkan(info)

        # Create .netkan file or quit if already there
        netkan_path = Path(self.netkan_repo.working_dir,
                           'NetKAN', f"{netkan.get('identifier')}.netkan")
        if netkan_path.exists():
            # Already exists, we are done
            return True
        # Otherwise create
        netkan_path.write_text(json.dumps(netkan))

        # Create branch
        branch_name = f"add-{netkan.get('identifier')}"
        try:
            self.netkan_repo.remotes.origin.fetch(branch_name)
        except git.GitCommandError:
            # *Shrug*
            pass
        if branch_name not in self.netkan_repo.heads:
            self.netkan_repo.create_head(
                branch_name,
                getattr(
                    self.netkan_repo.remotes.origin.refs,
                    branch_name
                )
            )
        # Checkout branch
        self.netkan_repo.heads[branch_name].checkout()

        # Add netkan to branch
        self.netkan_repo.index.add([netkan_path.as_posix()])

        # Commit
        self.netkan_repo.index.commit(
            (
                f"Add {info.get('name')} from {info.get('site_name')}"
                f"\n\nThis is an automated commit on behalf of {info.get('username')}"
            ),
            author=git.Actor(info.get('username'), info.get('email'))
        )

        # Push branch
        self.netkan_repo.remotes.origin.push('{mod}:{mod}'.format(mod=branch_name))

        # Create pull request
        self.github_pr.create_pull_request(
            title=f"Add {info.get('name')} from {info.get('site_name')}",
            branch=branch_name,
            body=self.PR_BODY_TEMPLATE.substitute(info)
        )
        return True

    @staticmethod
    def deletion_msg(msg):
        return {
            'Id':            msg.message_id,
            'ReceiptHandle': msg.receipt_handle,
        }

    def make_netkan(self, info):
        return {
            'spec_version': 'v1.4',
            'identifier': re.sub(r'\W+', '', info.get('name')),
            '$kref': f"#/ckan/spacedock/{info.get('id')}",
            'license': info.get('license').replace(' ', '-'),
            'x_via': f"Automated {info.get('site_name')} CKAN submission"
        }
