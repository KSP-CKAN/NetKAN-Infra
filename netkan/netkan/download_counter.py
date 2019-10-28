import json
import logging
import re
import requests
from pathlib import Path
from json.decoder import JSONDecodeError
from .metadata import Netkan
from .utils import repo_file_add_or_changed


class NetkanDownloads(Netkan):
    github_pattern = re.compile('^([^/]+)/([^/]+)')
    github_api = 'https://api.github.com/repos/'

    def __init__(self, filename=None, github_token=None, contents=None):
        super().__init__(filename, contents)
        self.github_headers = {'Authorization': f'token {github_token}'}
        self.github_token = github_token

    @property
    def spacedock_api(self):
        return f'https://spacedock.info/api/mod/{self.kref_id}'

    @property
    def github_repo_api(self):
        (user, repo) = self.github_pattern.match(self.kref_id).groups()
        return f'{self.github_api}{user}/{repo}'

    @property
    def curse_api(self):
        if self.kref_id.isnumeric():
            return f'https://api.cfwidget.com/project/{self.kref_id}'
        return f'https://api.cfwidget.com/kerbal/ksp-mods/{self.kref_id}'

    @property
    def remote_netkan(self):
        return self.kref_id

    def count_from_spacedock(self):
        return requests.get(self.spacedock_api).json()['downloads']

    def count_from_github(self, url=None):
        if not url:
            url = self.github_repo_api
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
            url = f"{self.github_api}{repo['parent']['full_name']}"
            total += self.count_from_github(url)
        return total

    def count_from_curse(self):
        return requests.get(self.curse_api).json()['downloads']['total']

    def count_from_netkan(self):
        return NetkanDownloads(
                github_token=self.github_token,
                contents=requests.get(self.remote_netkan).text
            ).get_count()

    def get_count(self):
        count = 0
        if self.has_kref:
            try:
                count = getattr(self, f'count_from_{self.kref_src}')()
            except JSONDecodeError as e:
                logging.error(f'Failed decoding count for {self.identifier}: {e}')
            except KeyError as e:
                logging.error(f'Download count key \'{e}\' missing from api for {self.identifier}')
            except AttributeError:
                # If the kref_src isn't defined, we haven't created a counter
                # for it and likely doesn't have one.
                pass
        return count


class DownloadCounter:

    def __init__(self, netkan_path, ckan_meta, github_token):
        self.netkan_path = Path(netkan_path)
        self.ckan_meta = ckan_meta
        self.counts = {}
        self.github_token = github_token
        self.output_file = Path(
            self.ckan_meta.working_dir, 'download_counts.json'
        )

    def get_counts(self):
        for netkan in self.netkan_path.glob('NetKAN/*.netkan'):
            netkan = NetkanDownloads(netkan, self.github_token)
            count = netkan.get_count()
            if count > 0:
                self.counts[netkan.identifier] = count

    def write_json(self):
        self.output_file.write_text(
            json.dumps(self.counts, sort_keys=True, indent=4)
        )

    def commit_counts(self):
        index = self.ckan_meta.index
        index.add([self.output_file.as_posix()])
        index.commit(
            'NetKAN Updating Download Counts'
        )
        logging.info('Download counts changed and commited')
        self.ckan_meta.remotes.origin.push('master')

    def update_counts(self):
        self.get_counts()
        self.ckan_meta.remotes.origin.pull(
            'master', strategy_option='ours'
        )
        self.write_json()
        if repo_file_add_or_changed(self.ckan_meta, self.output_file):
            self.commit_counts()
        else:
            logging.info('Download counts match existing data.')
