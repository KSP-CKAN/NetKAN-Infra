import json
import logging
import re
import requests
from pathlib import Path
from json.decoder import JSONDecodeError
from .utils import repo_file_add_or_changed


class DownloadCounter:

    def __init__(self, netkan_path, ckan_meta, github_token):
        self.netkan_path = Path(netkan_path)
        self.ckan_meta = ckan_meta
        self.github_headers = {'Authorization': f'token {github_token}'}
        self.kref_pattern = re.compile('^#/ckan/([^/]+)/(.+)$')
        self.github_pattern = re.compile('^([^/]+)/([^/]+)')
        self.counts = {}
        self.output_file = Path(
            self.ckan_meta.working_dir, 'download_counts.json'
        )

    def count_from_spacedock(self, mod_id):
        return requests.get(
            f'https://spacedock.info/api/mod/{mod_id}'
        ).json()['downloads']

    def count_from_github(self, mod_id):
        (user, repo) = self.github_pattern.match(mod_id).groups()
        releases = requests.get(
            f'https://api.github.com/repos/{user}/{repo}/releases',
            headers=self.github_headers
        ).json()

        total = 0
        for rel in releases:
            for asset in rel['assets']:
                total += asset['download_count']

        repo = requests.get(
            f'https://api.github.com/repos/{user}/{repo}',
            headers=self.github_headers
        ).json()
        if 'parent' in repo:
            total += self.count_from_github(repo['parent']['full_name'])
        return total

    def count_from_curse(self, mod_id):
        return requests.get(
            f'https://api.cfwidget.com/project/{mod_id}'
            if mod_id.isnumeric()
            else f'https://api.cfwidget.com/kerbal/ksp-mods/{mod_id}'
        ).json()['downloads']['total']

    def count_from_url(self, url):
        count = 0
        try:
            count = self.count_from_netkan(requests.get(url).json())
        except JSONDecodeError:
            logging.error("Failed to get count from {}".format(url))
        return count

    def count_from_netkan(self, netkan):
        kref = netkan.get('$kref', None)
        if not kref:
            return 0
        (kind, mod_id) = self.kref_pattern.match(kref).groups()
        if kind == 'netkan':
            return self.count_from_url(mod_id)
        elif kind == 'spacedock':
            return self.count_from_spacedock(mod_id)
        elif kind == 'github':
            return self.count_from_github(mod_id)
        elif kind == 'curse':
            return self.count_from_curse(mod_id)
        return 0

    def get_counts(self):
        for netkan in self.netkan_path.glob('NetKAN/*.netkan'):
            netkan = Path(netkan)

            # TODO: This downloader works, but needs refactoring. The error cases
            #       are awkward and there is a fair bit of duplication going on.
            count = 0
            try:
                count = self.count_from_netkan(
                    json.loads(netkan.read_text())
                )
            except JSONDecodeError:
                logging.error("Failed decoding count for  {}".format(netkan.stem))

            if count > 0:
                self.counts[netkan.stem] = count

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
            'master', strategy='ours'
        )
        self.write_json()
        if repo_file_add_or_changed(self.ckan_meta, self.output_file):
            self.commit_counts()
        else:
            logging.info('Download counts match existing data.')
