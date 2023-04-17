import logging
from datetime import datetime, timezone, timedelta
from typing import Iterable, Optional, List, Tuple

from .status import ModStatus
from .repos import NetkanRepo
from .github_pr import GitHubPR


class AutoFreezer:

    BRANCH_NAME = 'freeze/auto'

    def __init__(self, nk_repo: NetkanRepo, github_pr: GitHubPR, game_id: str) -> None:
        self.nk_repo = nk_repo
        self.github_pr = github_pr
        self.game_id = game_id

    def freeze_idle_mods(self, days_limit: int, days_till_ignore: int) -> None:
        self.nk_repo.pull_remote_primary(strategy_option='ours')
        idle_mods = self._find_idle_mods(days_limit, days_till_ignore)
        if idle_mods:
            with self.nk_repo.change_branch(self.BRANCH_NAME):
                for ident, _ in idle_mods:
                    if self.nk_repo.nk_path(ident).exists():
                        logging.info('Freezing %s', ident)
                        self._add_freezee(ident)
                    else:
                        logging.info('Already froze %s', ident)
            self._submit_pr(self.BRANCH_NAME, days_limit, idle_mods)

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

    def _ids(self) -> Iterable[str]:
        return (nk.identifier for nk in self.nk_repo.netkans())

    def _find_idle_mods(self, days_limit: int, days_till_ignore: int) -> List[Tuple[str, datetime]]:
        update_cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)
        too_old_cutoff = update_cutoff - timedelta(days=days_till_ignore)
        # I can't get a list comprehension to do this without the datetime becoming optional
        idle_mods = []
        for ident in self._ids():
            dttm = self._last_timestamp(ident)
            if dttm and too_old_cutoff < dttm < update_cutoff:
                idle_mods.append((ident, dttm))
        idle_mods.sort(key=lambda mod: mod[1])
        return idle_mods

    def _last_timestamp(self, ident: str) -> Optional[datetime]:
        try:
            status = ModStatus.get(ident, range_key=self.game_id.lower())
            return getattr(status, 'release_date',
                           getattr(status, 'last_indexed',
                                   None))
        except ModStatus.DoesNotExist:
            # No timestamp if mod isn't in the status table (very freshly merged)
            return None

    def _add_freezee(self, ident: str) -> None:
        self.nk_repo.git_repo.index.move([
            self.nk_repo.nk_path(ident).as_posix(),
            self.nk_repo.frozen_path(ident).as_posix()
        ])
        self.nk_repo.git_repo.index.commit(f'Freeze {ident}')

    def _mod_table(self, idle_mods: List[Tuple[str, datetime]]) -> str:
        return '\n'.join([
            'Mod | Last Update',
            ':-- | :--',
            *[f'{AutoFreezer._mod_cell(mod[0], self.game_id)} | {mod[1].astimezone(timezone.utc):%Y-%m-%d %H:%M %Z}'
              for mod in idle_mods]
        ])

    @staticmethod
    def _mod_cell(ident: str, game_id: str) -> str:
        status = ModStatus.get(ident, range_key=game_id.lower())
        resources = getattr(status, 'resources', None)
        if resources:
            links = r' \| '.join(f'[{key}]({url})'
                                 for key, url in sorted(resources.as_dict().items()))
            return f'**{ident}**<br>{links}'
        return f'**{ident}**'

    def _submit_pr(self, branch_name: str, days: int, idle_mods: List[Tuple[str, datetime]]) -> None:
        if self.github_pr:
            logging.info('Submitting pull request for %s', branch_name)
            self.github_pr.create_pull_request(
                branch=branch_name,
                title='Freeze idle mods',
                body=(f'The attached mods have not updated in {days} or more days.'
                      ' Freeze them to save the bot some CPU cycles.'
                      '\n\n'
                      f'{self._mod_table(idle_mods)}'),
                labels=['Pull request', 'Freeze', 'Needs looking into'],
            )
