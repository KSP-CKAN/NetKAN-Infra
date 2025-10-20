import json
import logging
import re
from pathlib import Path
from string import Template
import urllib.parse
from typing import Dict, Tuple, Any, Optional, Iterable
import heapq
from datetime import date, datetime, timezone, timedelta
from time import sleep
from itertools import groupby, batched
from more_itertools import ilen

import requests
from requests.exceptions import ConnectTimeout

from .utils import repo_file_add_or_changed, legacy_read_text
from .repos import CkanMetaRepo
from .metadata import Ckan


class GitHubBatchedQuery:

    PATH_PATTERN = re.compile(r'^/([^/]+)/([^/]+)')

    # The URL that handles GitHub GraphQL requests
    GITHUB_API = 'https://api.github.com/graphql'

    # Get this many modules per request
    MODULES_PER_GRAPHQL = 10

    # The request we send to GitHub, with a parameter for the module specific section
    GRAPHQL_TEMPLATE = Template(legacy_read_text('netkan', 'downloads_query.graphql'))

    # The request string per module, depends on getDownloads fragment existing in
    # the main template
    MODULE_TEMPLATE = Template(
        '${ident}: repository(owner: "${user}", name: "${repo}") { ...getDownloads }')

    def __init__(self, github_token: str) -> None:
        self.repos: Dict[str, Tuple[str, str]] = {}
        self.requests: Dict[Tuple[str, str], str] = {}
        self.cache: Dict[Tuple[str, str], int] = {}
        self.github_token = github_token
        logging.info('Starting new GraphQL query')

    def empty(self) -> bool:
        # We might need to return values that are already cached
        return len(self.repos) == 0

    def full(self) -> bool:
        # We only need to do requests for uncached mods
        return len(self.requests) >= self.MODULES_PER_GRAPHQL

    def add(self, identifier: str, user: str, repo: str) -> None:
        user_repo = (user, repo)
        self.repos[identifier] = user_repo
        # Queue this request if we haven't already
        if user_repo not in self.cache and user_repo not in self.requests:
            self.requests[user_repo] = identifier
        else:
            logging.debug('Skipping duplicate request for %s, %s, %s',
                          identifier, user, repo)

    def remove(self, identifier: str, user_repo: Tuple[str, str]) -> None:
        self.repos.pop(identifier, None)
        self.requests.pop(user_repo, None)
        # Keep self.cache for shared $krefs

    def get_queries(self) -> Iterable[str]:
        return map(self.get_query, batched(self.requests.items(),
                                           self.MODULES_PER_GRAPHQL))

    def get_query(self, reqs: Tuple[Tuple[Tuple[str, str], str], ...]) -> str:
        return self.GRAPHQL_TEMPLATE.safe_substitute(module_queries='\n'.join(
            self.get_module_query(identifier, user, repo)
            for (user, repo), identifier in reqs))

    def get_module_query(self, identifier: str, user: str, repo: str) -> str:
        return self.MODULE_TEMPLATE.safe_substitute(
            ident=self.graphql_safe_identifier(identifier),
            user=user, repo=repo)

    @staticmethod
    def graphql_safe_identifier(identifier: str) -> str:
        """
        Identifiers can start with numbers and include hyphens.
        GraphQL doesn't like that, so we put an 'x' on the front
        and replace dashes with underscores (which luckily CAN'T
        appear in identifiers, so this is reversible).
        """
        return f'x{identifier.replace("-", "_")}'

    @staticmethod
    def from_graphql_safe_identifier(fake_ident: str) -> str:
        """
        Inverse of the above. Strip off the first character and
        replace underscores with dashes, to get back to the original
        identifier.
        """
        return fake_ident[1:].replace("_", "-")

    def get_result(self, counts: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        if counts is None:
            counts = {}
        logging.info('Running GraphQL query')
        for full_query in list(self.get_queries()):
            result = self.graphql_to_github(full_query)
            if not result:
                continue
            if 'errors' in result:
                logging.error('DownloadCounter errors in GraphQL query: %s',
                              ', '.join(f'{msg} (x{ilen(grp)})'
                                        for msg, grp
                                        in groupby(sorted(err['message']
                                                          for err in result['errors'])))
                              if result['errors'] else 'Empty errors list')
            if 'data' in result:
                for fake_ident, apidata in result['data'].items():
                    if apidata:
                        real_ident = self.from_graphql_safe_identifier(fake_ident)
                        try:
                            count = self.sum_graphql_result(apidata)
                            user_repo = self.repos[real_ident]
                            # Cache results per repo, for shared $krefs
                            self.cache[user_repo] = count
                        except Exception:  # pylint: disable=broad-except
                            pass
        # Retrieve everything from the cache, new and old alike
        for ident, user_repo in list(self.repos.items()):
            if user_repo in self.cache:
                count = self.cache[user_repo]
                logging.info('Count for %s is %s', ident, count)
                counts[ident] = counts.get(ident, 0) + count
                # Purge completed requests
                self.remove(ident, user_repo)
        return counts

    def graphql_to_github(self, query: str) -> Optional[Dict[str, Any]]:
        logging.info('Contacting GitHub')
        for which_attempt in range(5):
            response = requests.post(self.GITHUB_API,
                                     headers={'Authorization': f'bearer {self.github_token}'},
                                     json={'query': query},
                                     timeout=60)
            retry_after = self._retry_interval(response)
            if retry_after:
                logging.error('Download counter throttled, waiting %s to retry...',
                              retry_after)
                sleep(retry_after.total_seconds() * (2 ** which_attempt))
            else:
                return response.json()
        logging.error('Download counter query ran out of retries')
        return None

    def _retry_interval(self, response: requests.Response) -> Optional[timedelta]:
        retry_after = response.headers.get('Retry-After', None)
        if retry_after:
            return timedelta(seconds=float(retry_after))

        remaining = response.headers.get('X-RateLimit-Remaining', None)
        reset = response.headers.get('X-RateLimit-Reset', None)
        if remaining and reset and float(remaining) == 0:
            return datetime.fromtimestamp(float(reset), timezone.utc) - datetime.now(timezone.utc)

        if response.status_code == 403:
            return timedelta(minutes=1)

        return None

    def sum_graphql_result(self, apidata: Dict[str, Any]) -> int:
        total = 0
        if apidata.get('parent', None):
            total += self.sum_graphql_result(apidata['parent'])
        for release in apidata['releases']['nodes']:
            for asset in release['releaseAssets']['nodes']:
                total += asset['downloadCount']
        return total


class SpaceDockBatchedQuery:

    PATH_PATTERN = re.compile(r'^/mod/([^/]+)')

    SPACEDOCK_API = 'https://spacedock.info/api/download_counts'

    def __init__(self) -> None:
        self.ids: Dict[str, int] = {}

    def empty(self) -> bool:
        return len(self.ids) == 0

    def add(self, identifier: str, sd_id: int) -> None:
        self.ids[identifier] = sd_id

    def get_query(self) -> Dict[str, Any]:
        return {
            # Ensure uniqueness for shared $krefs
            'mod_id': list(set(self.ids.values()))
        }

    def query_to_spacedock(self, query: Dict[str, Any]) -> Dict[str, Any]:
        return requests.post(self.SPACEDOCK_API, data=query, timeout=60).json()

    def get_result(self, counts: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        if counts is None:
            counts = {}
        full_query = self.get_query()
        result = self.query_to_spacedock(full_query)
        sd_counts = {
            element.get('id'): element.get('downloads')
            for element in result.get('download_counts', [])
        }
        for identifier, sd_id in self.ids.items():
            count = sd_counts.get(sd_id)
            if count:
                logging.info('Count for %s is %s', identifier, count)
                counts[identifier] = counts.get(identifier, 0) + count
        return counts


class InternetArchiveBatchedQuery:

    # https://archive.org/services/docs/api/views_api.html
    IARCHIVE_API = 'https://be-api.us.archive.org/views/v1/short/'

    # It let me get away with 35 in testing, let's pad that
    MODULES_PER_REQUEST = 30

    def __init__(self) -> None:
        self.ids: Dict[str, str] = {}

    def empty(self) -> bool:
        return len(self.ids) == 0

    def full(self) -> bool:
        return len(self.ids) >= self.MODULES_PER_REQUEST

    def add(self, ckan: Ckan) -> None:
        self.ids[ckan.identifier] = ckan.mirror_item()

    def get_result(self, counts: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        if counts is None:
            counts = {}
        result = requests.get(self.IARCHIVE_API + ','.join(self.ids.values()),
                              timeout=60).json()
        for ckan_ident, ia_ident in self.ids.items():
            try:
                counts[ckan_ident] = counts.get(ckan_ident, 0) + result[ia_ident]['all_time']
            except KeyError as exc:
                logging.error('InternetArchive id not found in downloads result: %s',
                              ia_ident, exc_info=exc)
        return counts


class SourceForgeQuerier:

    PATH_PATTERN = re.compile(r'^/project/([^/]+)')

    # https://sourceforge.net/p/forge/documentation/Download%20Stats%20API/
    API_TEMPLATE = Template('https://sourceforge.net/projects/${proj_id}/files/stats/json'
                            '?start_date=2010-01-01&end_date=${today}'
                            '&os_by_country=false&period=monthly')

    @classmethod
    def get_count(cls, proj_id: str) -> int:
        return requests.get(cls.get_query(proj_id), timeout=60).json()['total']

    @classmethod
    def get_query(cls, proj_id: str) -> str:
        return cls.API_TEMPLATE.safe_substitute(proj_id=proj_id,
                                                today=date.today().isoformat())

    @classmethod
    def get_result(cls, ident: str, proj_id: str,
                   counts: Optional[Dict[str, int]] = None) -> Dict[str, int]:
        if counts is None:
            counts = {}
        counts[ident] = counts.get(ident, 0) + cls.get_count(proj_id)
        return counts


class DownloadCounter:

    def __init__(self, game_id: str, ckm_repo: CkanMetaRepo, github_token: str) -> None:
        self.game_id = game_id
        self.ckm_repo = ckm_repo
        self.counts: Dict[str, Any] = {}
        self.github_token = github_token
        if self.ckm_repo.git_repo.working_dir:
            self.output_file = Path(
                self.ckm_repo.git_repo.working_dir, 'download_counts.json'
            )

    def get_counts(self) -> None:
        graph_query = GitHubBatchedQuery(self.github_token)
        sd_query = SpaceDockBatchedQuery()
        ia_query: Optional[InternetArchiveBatchedQuery] = InternetArchiveBatchedQuery()
        for ckan in self.ckm_repo.all_latest_modules():  # pylint: disable=too-many-nested-blocks
            if ckan.kind == 'dlc':
                continue
            for download in ckan.downloads:
                try:
                    url_parse = urllib.parse.urlparse(download)
                    if url_parse.netloc == 'github.com':
                        match = GitHubBatchedQuery.PATH_PATTERN.match(url_parse.path)
                        if match:
                            # Process GitHub modules together in big batches
                            graph_query.add(ckan.identifier, *match.groups())
                            if graph_query.full():
                                # Run the query
                                graph_query.get_result(self.counts)
                    elif url_parse.netloc == 'spacedock.info':
                        match = SpaceDockBatchedQuery.PATH_PATTERN.match(url_parse.path)
                        if match:
                            # Process SpaceDock modules together in one huge batch
                            sd_query.add(ckan.identifier, int(match.group(1)))
                        else:
                            logging.error('Failed to parse SD URL for %s: %s',
                                          ckan.identifier, download)
                    elif url_parse.netloc == 'archive.org':
                        if ia_query:
                            ia_query.add(ckan)
                            if ia_query.full():
                                try:
                                    ia_query.get_result(self.counts)
                                    ia_query = InternetArchiveBatchedQuery()
                                except ConnectTimeout as exc:
                                    # Cleanly turn off archive.org counting during downtime
                                    logging.error('Failed to get counts from archive.org',
                                                  exc_info=exc)
                                    ia_query = None
                    elif url_parse.netloc.endswith('.sourceforge.net'):
                        match = SourceForgeQuerier.PATH_PATTERN.match(url_parse.path)
                        if match:
                            SourceForgeQuerier.get_result(ckan.identifier, match.group(1),
                                                          self.counts)
                        else:
                            logging.error('Failed to parse SF URL for %s: %s',
                                          ckan.identifier, download)
                except Exception as exc:  # pylint: disable=broad-except
                    # Don't let one bad apple spoil the bunch
                    # Print file path because netkan_dl might be None
                    logging.error('DownloadCounter failed for %s',
                                  ckan.identifier, exc_info=exc)
        if not sd_query.empty():
            sd_query.get_result(self.counts)
        if not graph_query.empty():
            # Final pass doesn't overflow the bound
            graph_query.get_result(self.counts)
        if ia_query and not ia_query.empty():
            ia_query.get_result(self.counts)

    def write_json(self) -> None:
        if self.output_file:
            self.output_file.write_text(
                json.dumps(self.counts, sort_keys=True, indent=4),
                encoding='UTF-8'
            )

    def commit_counts(self) -> None:
        if self.output_file:
            self.ckm_repo.commit([self.output_file.as_posix()],
                                 'NetKAN updating download counts')
            logging.info('Download counts changed and committed')
            self.ckm_repo.push_remote_primary()

    @staticmethod
    def _download_summary_table(counts: Dict[str, int], how_many: int) -> str:
        return '\n'.join(f'    {counts[ident]:8}  {ident}'
                         for ident in heapq.nlargest(how_many, counts, lambda i: counts.get(i, 0))
                         if counts[ident] > 0)

    def log_top(self, how_many: int) -> None:
        if self.output_file and self.output_file.exists():
            with open(self.output_file, encoding='UTF-8') as old_file:
                old_counts = json.load(old_file)
                deltas = {ident: count - old_counts[ident]
                          for ident, count in self.counts.items()
                          if ident in old_counts}
                # This isn't an error, but only errors go to Discord
                logging.error('Top %s downloads for %s all-time:\n%s\n\n'
                              'Top %s downloads for %s today:\n%s',
                              how_many, self.game_id,
                              self._download_summary_table(self.counts, how_many),
                              how_many, self.game_id,
                              self._download_summary_table(deltas, how_many))

    def update_counts(self) -> None:
        if self.output_file:
            self.get_counts()
            self.ckm_repo.pull_remote_primary(strategy_option='ours')
            self.log_top(5)
            self.write_json()
            if repo_file_add_or_changed(self.ckm_repo.git_repo, self.output_file):
                self.commit_counts()
            else:
                logging.info('Download counts match existing data.')
