import logging
import os
import json
import requests
import re
from datetime import datetime
from pathlib import Path

class DownloadCounter:

    def __init__(self, netkan_repo, ckan_meta_repo, github_token):
        self.netkan_repo    = netkan_repo
        self.ckan_meta_repo = ckan_meta_repo

        self.github_headers = { 'Authorization': f'token {github_token}' }
        self.kref_pattern   = re.compile('^#/ckan/([^/]+)/(.+)$')
        self.github_pattern = re.compile('^([^/]+)/([^/]+)')
        self.counts         = {}
        self.output_file    = Path(self.ckan_meta_repo.working_dir, 'download_counts.json')

    def count_from_spacedock(id):
        return requests.get(f'https://spacedock.info/api/mod/{id}').json()['downloads']

    def count_from_github(id):
        (user, repo) = self.github_pattern.match(id).groups()
        releases = requests.get(
            f'https://api.github.com/repos/{user}/{repo}/releases',
            headers = self.github_headers
        ).json()

        sum = 0
        for rel in releases:
            for asset in rel['assets']:
               sum += asset['download_count']

        repo = requests.get(
            f'https://api.github.com/repos/{user}/{repo}',
            headers = self.github_headers
        ).json()
        if 'parent' in repo:
            sum += count_from_github(repo['parent']['full_name'])
        return sum

    def count_from_curse(id):
        return requests.get(
            f'https://api.cfwidget.com/project/{id}'
            if id.isnumeric()
            else f'https://api.cfwidget.com/kerbal/ksp-mods/{id}'
        ).json()['downloads']['total']

    def count_from_netkan(netkan):
        kref = netkan['$kref']
        if not kref is None:
            (kind, id) = self.kref_pattern.match(kref).groups()
            if   kind == 'netkan':    return count_from_url(id)
            elif kind == 'spacedock': return count_from_spacedock(id)
            elif kind == 'github':    return count_from_github(id)
            elif kind == 'curse':     return count_from_curse(id)

    def count_from_url(url):
        return count_from_netkan(requests.get(url).json())

    def count_from_file(file):
        with open(file) as netkan_file:
            return count_from_netkan(json.load(netkan_file))

    def get_counts():
        for netkan in self.netkan_repo.working_dir.glob('NetKAN/*.netkan'):
            count = count_from_file(netkan)
            if not count is None and count > 0:
                self.counts[os.path.basename(netkan)] = count

    def write_json():
        with open(self.output_file, 'w') as outfile:
            json.dump(self.counts, outfile, sort_keys=True, indent=4)

    def last_run():
        return datetime.fromtimestamp(self.ckan_meta_repo.master.log(
            # Just the most recent commit for this file
            '--max-count=1',
            # Get output in epoch+tz format
            "--pretty=%ad", '--date=raw',
            '--',
            self.output_file
        ))
