import json
import logging
import re
from pathlib import Path
from importlib.resources import read_text
from string import Template
import urllib.parse
from typing import Dict, Tuple, Any

import requests

from .utils import repo_file_add_or_changed
from .repos import CkanMetaRepo
from .metadata import Ckan


class GraphQLQuery:

    # The URL that handles GitHub GraphQL requests
    GITHUB_API = 'https://api.github.com/graphql'

    # Get this many modules per request
    MODULES_PER_GRAPHQL = 40

    # The request we send to GitHub, with a parameter for the module specific section
    GRAPHQL_TEMPLATE = Template(read_text('netkan', 'downloads_query.graphql'))

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

    def clear(self) -> None:
        self.repos.clear()
        self.requests.clear()
        # Keep self.cache for shared $krefs

    def get_query(self) -> str:
        return self.GRAPHQL_TEMPLATE.safe_substitute(module_queries="\n".join(
            filter(None, [self.get_module_query(identifier, user, repo)
                          for (user, repo), identifier
                          in self.requests.items()])))

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

    def get_result(self, counts: Dict[str, int] = None) -> Dict[str, int]:
        if counts is None:
            counts = {}
        logging.info('Running GraphQL query')
        full_query = self.get_query()
        result = self.graphql_to_github(full_query)
        if 'errors' in result:
            logging.error('DownloadCounter errors in GraphQL query: %s',
                ', '.join(err['message'] for err in result['errors'])
                if result['errors'] else 'Empty errors list')
        if 'data' in result:
            for fake_ident, apidata in result['data'].items():
                if apidata:
                    real_ident = self.from_graphql_safe_identifier(fake_ident)
                    count = self.sum_graphql_result(apidata)
                    user_repo = self.repos[real_ident]
                    # Cache results per repo, for shared $krefs
                    self.cache[user_repo] = count
        # Retrieve everything from the cache, new and old alike
        for ident, user_repo in self.repos.items():
            if user_repo in self.cache:
                count = self.cache[user_repo]
                logging.info('Count for %s is %s', ident, count)
                counts[ident] = count
        return counts

    def graphql_to_github(self, query: str) -> Dict[str, Any]:
        logging.info('Contacting GitHub')
        return requests.post(self.GITHUB_API,
                             headers={'Authorization': f'bearer {self.github_token}'},
                             json={'query': query},
                             timeout=60).json()

    def sum_graphql_result(self, apidata: Dict[str, Any]) -> int:
        total = 0
        if apidata.get('parent', None):
            total += self.sum_graphql_result(apidata['parent'])
        for release in apidata['releases']['nodes']:
            for asset in release['releaseAssets']['nodes']:
                total += asset['downloadCount']
        return total


class SpaceDockBatchedQuery:

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

    def get_result(self, counts: Dict[str, int] = None) -> Dict[str, int]:
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
                counts[identifier] = count
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

    def _get_ia_ident(self, ckan: Ckan) -> str:
        return f'{ckan.identifier}-{ckan.version.string.replace(":", "-")}'

    def add(self, ckan: Ckan) -> None:
        self.ids[ckan.identifier] = self._get_ia_ident(ckan)

    def get_result(self, counts: Dict[str, int] = None) -> Dict[str, int]:
        if counts is None:
            counts = {}
        result = requests.get(self.IARCHIVE_API + ','.join(self.ids.values()),
                              timeout=60).json()
        for ckan_ident, ia_ident in self.ids.items():
            counts[ckan_ident] = result[ia_ident]['all_time']
        return counts


class DownloadCounter:

    GITHUB_PATH_PATTERN = re.compile(r'^/([^/]+)/([^/]+)')
    SPACEDOCK_PATH_PATTERN = re.compile(r'^/mod/([^/]+)')

    def __init__(self, ckm_repo: CkanMetaRepo, github_token: str) -> None:
        self.ckm_repo = ckm_repo
        self.counts: Dict[str, Any] = {}
        self.github_token = github_token
        if self.ckm_repo.git_repo.working_dir:
            self.output_file = Path(
                self.ckm_repo.git_repo.working_dir, 'download_counts.json'
            )

    def get_counts(self) -> None:
        graph_query = GraphQLQuery(self.github_token)
        sd_query = SpaceDockBatchedQuery()
        ia_query = InternetArchiveBatchedQuery()
        for ckan in self.ckm_repo.all_latest_modules():
            if ckan.kind == 'dlc':
                continue
            try:
                url_parse = urllib.parse.urlparse(ckan.download)
                if url_parse.netloc == 'github.com':
                    match = self.GITHUB_PATH_PATTERN.match(url_parse.path)
                    if match:
                        # Process GitHub modules together in big batches
                        graph_query.add(ckan.identifier, *match.groups())
                        if graph_query.full():
                            # Run the query
                            graph_query.get_result(self.counts)
                            # Clear request list
                            graph_query.clear()
                elif url_parse.netloc == 'spacedock.info':
                    match = self.SPACEDOCK_PATH_PATTERN.match(url_parse.path)
                    if match:
                        # Process SpaceDock modules together in one huge batch
                        sd_query.add(ckan.identifier, int(match.group(1)))
                    else:
                        logging.error('Failed to parse SD URL for %s: %s',
                                      ckan.identifier, ckan.download)
                elif url_parse.netloc == 'archive.org':
                    ia_query.add(ckan)
                    if ia_query.full():
                        ia_query.get_result(self.counts)
                        ia_query = InternetArchiveBatchedQuery()
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
        if not ia_query.empty():
            ia_query.get_result(self.counts)

    def write_json(self) -> None:
        if self.output_file:
            self.output_file.write_text(
                json.dumps(self.counts, sort_keys=True, indent=4),
                encoding='UTF-8'
            )

    def commit_counts(self) -> None:
        if self.output_file:
            self.ckm_repo.commit(
                [self.output_file.as_posix()],
                'NetKAN Updating Download Counts'
            )
            logging.info('Download counts changed and committed')
            self.ckm_repo.git_repo.remotes.origin.push('master')

    def update_counts(self) -> None:
        if self.output_file:
            self.get_counts()
            self.ckm_repo.git_repo.remotes.origin.pull(
                'master', strategy_option='ours'
            )
            self.write_json()
            if repo_file_add_or_changed(self.ckm_repo.git_repo, self.output_file):
                self.commit_counts()
            else:
                logging.info('Download counts match existing data.')
