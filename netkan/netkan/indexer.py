import hashlib
import logging
from pathlib import Path, PurePath
from collections import deque
from datetime import datetime, timezone
from contextlib import contextmanager
from dateutil.parser import parse
from git import GitCommandError

from .metadata import Ckan
from .status import ModStatus


class CkanMessage:

    def __init__(self, msg, ckan_meta, github_pr=None):
        self.body = msg.body
        self.ckan = Ckan(contents=self.body)
        self.ErrorMessage = None
        self.indexed = False
        for item in msg.message_attributes.items():
            attr_type = '{}Value'.format(item[1]['DataType'])
            content = item[1][attr_type]
            if content.lower() in ['true', 'false']:
                content = True if content.lower() == 'true' else False
            if item[0] == 'FileName':
                content = PurePath(content).name
            setattr(self, item[0], content)
        self.md5_of_body = msg.md5_of_body
        self.message_id = msg.message_id
        self.receipt_handle = msg.receipt_handle
        self.ckan_meta = ckan_meta
        self.github_pr = github_pr

    def __str__(self):
        return '{}: {}'.format(self.ModIdentifier, self.CheckTime)

    @property
    def mod_path(self):
        return Path(self.ckan_meta.working_dir, self.ModIdentifier)

    @property
    def mod_file(self):
        return Path(self.mod_path, self.FileName)

    @property
    def mod_version(self):
        return self.mod_file.stem

    def mod_file_md5(self):
        with open(self.mod_file, mode='rb') as file:
            return hashlib.md5(file.read()).hexdigest()

    def metadata_changed(self):
        if not self.mod_file.exists():
            return True
        if self.mod_file_md5() == self.md5_of_body:
            return False
        return True

    def write_metadata(self):
        self.mod_path.mkdir(exist_ok=True)
        with open(self.mod_file, mode='w') as file:
            file.write(self.body)

    def commit_metadata(self):
        index = self.ckan_meta.index
        index.add([self.mod_file.as_posix()])
        commit = index.commit(
            'NetKAN generated mods - {}'.format(self.mod_version)
        )
        logging.info('Committing %s', self.mod_version)
        self.indexed = True
        return commit

    @contextmanager
    def change_branch(self):
        try:
            self.ckan_meta.remotes.origin.fetch(self.mod_version)
            if self.mod_version not in self.ckan_meta.heads:
                self.ckan_meta.create_head(
                    self.mod_version,
                    getattr(
                        self.ckan_meta.remotes.origin.refs,
                        self.mod_version
                    )
                )
            branch = getattr(
                self.ckan_meta.heads, self.mod_version
            )
            branch.checkout()
        except GitCommandError:
            if self.mod_version not in self.ckan_meta.heads:
                branch = self.ckan_meta.create_head(self.mod_version)
            else:
                branch = getattr(
                    self.ckan_meta.heads, self.mod_version
                )
            branch.checkout()
        try:
            yield
        finally:
            if self.indexed:
                # It's unlikely will hit a scenario where the metadata has
                # changed upstream of us, but the bot should win if it does.
                try:
                    self.ckan_meta.remotes.origin.pull(
                        self.mod_version, strategy_option='ours'
                    )
                except GitCommandError:
                    pass
                self.ckan_meta.remotes.origin.push(
                    '{mod}:{mod}'.format(mod=self.mod_version)
                )
            self.ckan_meta.heads.master.checkout()

    def status_attrs(self, new=False):
        inflation_time = parse(self.CheckTime)
        attrs = {
            'success': self.Success,
            'last_error': self.ErrorMessage,
            # We may wish to change the name in the inflator
            # as the index will set 'last_checked'
            'last_inflated': inflation_time,
            # If we have perfomed an inflation, we certainly
            # have checked the mod!
            'last_checked': inflation_time,
            # If we're inflating it, it's not frozen
            'frozen': False,
        }
        resources = getattr(self.ckan, 'resources', None)
        if resources:
            attrs['resources'] = resources
        if new:
            attrs['ModIdentifier'] = self.ModIdentifier
        if self.indexed:
            attrs['last_indexed'] = datetime.now(timezone.utc)
        return attrs

    def _process_ckan(self):
        if self.Success and self.metadata_changed():
            self.write_metadata()
            self.commit_metadata()
        try:
            status = ModStatus.get(self.ModIdentifier)
            attrs = self.status_attrs()
            if not self.Success and getattr(status, 'last_error', None) != self.ErrorMessage:
                logging.error('New inflation error for %s: %s',
                              self.ModIdentifier, self.ErrorMessage)
            actions = [
                getattr(ModStatus, key).set(
                    attrs[key]
                ) for key in attrs
            ]
            status.update(actions=actions)
        except ModStatus.DoesNotExist:
            ModStatus(**self.status_attrs(True)).save()

    def process_ckan(self):
        # Process regular CKAN
        if not self.Staged:
            self._process_ckan()
            return

        # TODO: This is a bit of hack to get this across the line, no mod
        #       version, no valid name to stage the branch
        if not self.Success:
            self._process_ckan()
            return

        # Staging operations
        with self.change_branch():
            self._process_ckan()
        if self.indexed:
            self.github_pr.create_pull_request(
                title=f'NetKAN inflated: {self.ModIdentifier}',
                branch=self.mod_version,
                body=getattr(self, 'StagingReason',
                             f'{self.ModIdentifier} has been staged, please test and merge')
            )

    @property
    def delete_attrs(self):
        return {
            'Id': self.message_id,
            'ReceiptHandle': self.receipt_handle
        }


class MessageHandler:

    def __init__(self, repo, github_pr=None):
        self.repo = repo
        self.github_pr = github_pr
        self.master = deque()
        self.staged = deque()
        self.processed = []

    def __str__(self):
        return str(self.master + self.staged)

    def __len__(self):
        return len(self.master + self.staged)

    # Apparently gitpython can be leaky on long running processes
    # we can ensure we call close on it and run our handler inside
    # a context manager
    def __enter__(self):
        if str(self.repo.active_branch) != 'master':
            self.repo.heads.master.checkout()
        self.repo.remotes.origin.pull('master', strategy_option='ours')
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.repo.close()

    def append(self, message):
        ckan = CkanMessage(
            message,
            self.repo,
            self.github_pr
        )
        if not ckan.Staged:
            self.master.append(ckan)
        else:
            self.staged.append(ckan)

    def _process_queue(self, queue):
        while queue:
            ckan = queue.popleft()
            ckan.process_ckan()
            self.processed.append(ckan)

    def sqs_delete_entries(self):
        return [c.delete_attrs for c in self.processed]

    # Currently we intermingle Staged/Master commits
    # separating them out will be a little more efficient
    # with our push/pull traffic.
    def process_ckans(self):
        self._process_queue(self.master)
        if any(ckan.indexed for ckan in self.processed):
            self.repo.remotes.origin.pull('master', strategy_option='ours')
            self.repo.remotes.origin.push('master')
        self._process_queue(self.staged)
