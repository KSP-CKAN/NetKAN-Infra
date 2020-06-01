import json
import logging
import re
from pathlib import Path
from json.decoder import JSONDecodeError
import requests
import git
from typing import Optional, Dict, Any

from .metadata import Netkan
from .utils import repo_file_add_or_changed
from .repos import NetkanRepo, CkanMetaRepo


class NetkanDownloads(Netkan):
    GITHUB_PATTERN = re.compile('^([^/]+)/([^/]+)')
    GITHUB_API = 'https://api.github.com/repos/'

    def __init__(self, filename: Path = None, github_token: str = None, contents: str = None) -> None:
        super().__init__(filename, contents)
        self.github_headers = {'Authorization': f'token {github_token}'}
        self.github_token = github_token

    @property
    def spacedock_api(self) -> str:
        return f'https://spacedock.info/api/mod/{self.kref_id}'

    @property
    def github_repo_api(self) -> Optional[str]:
        if self.kref_id:
            match = self.GITHUB_PATTERN.match(self.kref_id)
            if match:
                (user, repo) = match.groups()
                return f'{self.GITHUB_API}{user}/{repo}'
        return None

    @property
    def curse_api(self) -> str:
        if self.kref_id and self.kref_id.isnumeric():
            return f'https://api.cfwidget.com/project/{self.kref_id}'
        return f'https://api.cfwidget.com/kerbal/ksp-mods/{self.kref_id}'

    @property
    def remote_netkan(self) -> Optional[str]:
        return self.kref_id

    def count_from_spacedock(self) -> int:
        return requests.get(self.spacedock_api).json()['downloads']

    def count_from_github(self, url: str = None) -> int:
        if not url:
            url = self.github_repo_api
        if not url:
            return 0
        releases = requests.get(
            f'{url}/releases', headers=self.github_headers
        ).json()

        total = 0
        if isinstance(releases, list):
            for rel in releases:
                for asset in rel['assets']:
                    total += asset['download_count']

        repo = requests.get(
            url, headers=self.github_headers
        ).json()
        if 'parent' in repo:
            url = f"{self.GITHUB_API}{repo['parent']['full_name']}"
            total += self.count_from_github(url)
        return total

    def count_from_curse(self) -> int:
        return requests.get(self.curse_api).json()['downloads']['total']

    def count_from_netkan(self) -> int:
        if self.remote_netkan:
            return NetkanDownloads(
                github_token=self.github_token,
                contents=requests.get(self.remote_netkan).text
            ).get_count()
        return 0

    def get_count(self) -> int:
        count = 0
        if self.has_kref:
            try:
                count = getattr(self, f'count_from_{self.kref_src}')()
            except JSONDecodeError as exc:
                logging.error(
                    'Failed decoding count for %s: %s',
                    self.identifier, exc)
            except KeyError as exc:
                logging.error(
                    'Download count key \'%s\' missing from api for %s',
                    exc, self.identifier)
            except requests.exceptions.RequestException as exc:
                logging.error('Count retrieval failed for %s: %s',
                              self.identifier, exc)
            except AttributeError:
                # If the kref_src isn't defined, we haven't created a counter
                # for it and likely doesn't have one.
                logging.info('Can\'t get count for %s via %s', self.identifier, self.kref_src)
        return count


class DownloadCounter:

    def __init__(self, nk_repo: NetkanRepo, ckm_repo: CkanMetaRepo, github_token: str) -> None:
        self.nk_repo = nk_repo
        self.ckm_repo = ckm_repo
        self.counts: Dict[str, Any] = {}
        self.github_token = github_token
        self.output_file = Path(
            self.ckm_repo.git_repo.working_dir, 'download_counts.json'
        )

    def get_counts(self) -> None:
        for netkan in self.nk_repo.all_nk_paths():
            netkanDl = NetkanDownloads(netkan, self.github_token)
            count = netkanDl.get_count()
            if count > 0:
                logging.info('Count for %s is %s', netkanDl.identifier, count)
                self.counts[netkanDl.identifier] = count

    def write_json(self) -> None:
        self.output_file.write_text(
            json.dumps(self.counts, sort_keys=True, indent=4)
        )

    def commit_counts(self) -> None:
        index = self.ckm_repo.git_repo.index
        index.add([self.output_file.as_posix()])
        index.commit(
            'NetKAN Updating Download Counts'
        )
        logging.info('Download counts changed and commited')
        self.ckm_repo.git_repo.remotes.origin.push('master')

    def update_counts(self) -> None:
        self.get_counts()
        self.ckm_repo.git_repo.remotes.origin.pull(
            'master', strategy_option='ours'
        )
        self.write_json()
        if repo_file_add_or_changed(self.ckm_repo.git_repo, self.output_file):
            self.commit_counts()
        else:
            logging.info('Download counts match existing data.')
