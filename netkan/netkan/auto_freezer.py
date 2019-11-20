import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
import git

from .status import ModStatus


class AutoFreezer:

    BRANCH_NAME = 'freeze/auto'
    UNFROZEN_SUFFIX = 'netkan'
    FROZEN_SUFFIX = 'frozen'

    def __init__(self, netkan_repo, github_pr):
        self.netkan_repo = netkan_repo
        self.github_pr = github_pr

    def freeze_idle_mods(self, days_limit):
        update_cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)
        self.netkan_repo.remotes.origin.pull('master', strategy_option='ours')
        ids_to_freeze = [ident for ident in self._ids() if self._too_old(ident, update_cutoff)]
        if ids_to_freeze:
            self._checkout_branch(self.BRANCH_NAME)
            for ident in ids_to_freeze:
                if Path(self.netkan_repo.working_dir,
                        'NetKAN',
                        f'{ident}.{self.UNFROZEN_SUFFIX}'
                        ).exists():
                    logging.info('Freezing %s', ident)
                    self._add_freezee(ident)
                else:
                    logging.info('Already froze %s', ident)
            self._submit_pr(self.BRANCH_NAME, days_limit)
            self.netkan_repo.heads.master.checkout()

    def mark_frozen_mods(self):
        with ModStatus.batch_write() as batch:
            logging.info('Marking frozen mods...')
            for mod in ModStatus.scan(rate_limit=5):
                if not mod.frozen and self._is_frozen(mod.ModIdentifier):
                    logging.info('Marking frozen: %s', mod.ModIdentifier)
                    mod.frozen = True
                    batch.save(mod)
            logging.info('Done!')

    def _is_frozen(self, ident):
        return not Path(self.netkan_repo.working_dir, 'NetKAN', f'{ident}.netkan').exists()

    def _checkout_branch(self, name):
        try:
            self.netkan_repo.remotes.origin.fetch(name)
        except git.GitCommandError:
            logging.info('Unable to fetch %s', name)

        (getattr(self.netkan_repo.heads, name, None)
         or self.netkan_repo.create_head(name)).checkout()

    def _ids(self):
        return (nk_path.stem for nk_path
                in Path(self.netkan_repo.working_dir, "NetKAN").glob('*.netkan'))

    def _too_old(self, ident, update_cutoff):
        status = ModStatus.get(ident)
        last_indexed = getattr(status, 'last_indexed', None)
        if not last_indexed:
            # Never indexed since the start of status tracking = 4+ years old
            # ... except for mods that were updated by the old webhooks :(
            return False
        else:
            return last_indexed < update_cutoff

    def _add_freezee(self, ident):
        self.netkan_repo.index.move([
            Path('NetKAN', f'{ident}.{self.UNFROZEN_SUFFIX}').as_posix(),
            Path('NetKAN', f'{ident}.{self.FROZEN_SUFFIX}').as_posix()
        ])
        self.netkan_repo.index.commit(f'Freeze {ident}')

    def _submit_pr(self, branch_name, days):
        logging.info('Submitting pull request for %s', branch_name)
        self.netkan_repo.remotes.origin.push(f'{branch_name}:{branch_name}')
        self.github_pr.create_pull_request(
            branch=branch_name,
            title='Freeze idle mods',
            body=(f'The attached mods have not updated in {days} or more days.'
                  ' Freeze them to save the bot some CPU cycles.'),
        )
