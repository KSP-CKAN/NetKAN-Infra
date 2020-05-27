import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import git
from typing import Iterable

from .status import ModStatus
from .repos import NetkanRepo
from .github_pr import GitHubPR


class AutoFreezer:

    BRANCH_NAME = 'freeze/auto'

    def __init__(self, nk_repo: NetkanRepo, github_pr: GitHubPR = None) -> None:
        self.nk_repo = nk_repo
        self.github_pr = github_pr

    def freeze_idle_mods(self, days_limit: int) -> None:
        update_cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)
        self.nk_repo.git_repo.remotes.origin.pull('master', strategy_option='ours')
        ids_to_freeze = [ident for ident in self._ids() if self._too_old(ident, update_cutoff)]
        if ids_to_freeze:
            self._checkout_branch(self.BRANCH_NAME)
            for ident in ids_to_freeze:
                if self.nk_repo.nk_path(ident).exists():
                    logging.info('Freezing %s', ident)
                    self._add_freezee(ident)
                else:
                    logging.info('Already froze %s', ident)
            self._submit_pr(self.BRANCH_NAME, days_limit)
            self.nk_repo.git_repo.heads.master.checkout()

    def mark_frozen_mods(self) -> None:
        with ModStatus.batch_write() as batch:
            logging.info('Marking frozen mods...')
            for mod in ModStatus.scan(rate_limit=5):
                if not mod.frozen and self._is_frozen(mod.ModIdentifier):
                    logging.info('Marking frozen: %s', mod.ModIdentifier)
                    mod.frozen = True
                    batch.save(mod)
            logging.info('Done!')

    def _is_frozen(self, ident: str) -> bool:
        return not self.nk_repo.nk_path(ident).exists()

    def _checkout_branch(self, name: str) -> None:
        try:
            self.nk_repo.git_repo.remotes.origin.fetch(name)
        except git.GitCommandError:
            logging.info('Unable to fetch %s', name)

        (getattr(self.nk_repo.git_repo.heads, name, None)
         or self.nk_repo.git_repo.create_head(name)).checkout()

    def _ids(self) -> Iterable[str]:
        return (nk.identifier for nk in self.nk_repo.netkans())

    def _too_old(self, ident: str, update_cutoff: datetime) -> bool:
        status = ModStatus.get(ident)
        last_indexed = getattr(status, 'last_indexed', None)
        if not last_indexed:
            # Never indexed since the start of status tracking = 4+ years old
            # ... except for mods that were updated by the old webhooks :(
            return False
        else:
            return last_indexed < update_cutoff

    def _add_freezee(self, ident: str) -> None:
        self.nk_repo.git_repo.index.move([
            self.nk_repo.nk_path(ident).as_posix(),
            self.nk_repo.frozen_path(ident).as_posix()
        ])
        self.nk_repo.git_repo.index.commit(f'Freeze {ident}')

    def _submit_pr(self, branch_name: str, days: int) -> None:
        if self.github_pr:
            logging.info('Submitting pull request for %s', branch_name)
            self.nk_repo.git_repo.remotes.origin.push(f'{branch_name}:{branch_name}')
            self.github_pr.create_pull_request(
                branch=branch_name,
                title='Freeze idle mods',
                body=(f'The attached mods have not updated in {days} or more days.'
                      ' Freeze them to save the bot some CPU cycles.'),
            )
