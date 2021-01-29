import json
import logging
import re
from pathlib import Path
from json.decoder import JSONDecodeError
from importlib.resources import read_text
from string import Template
from typing import Optional, Dict, Any
import requests

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


class GraphQLQuery:

    # The URL that handles GitHub GraphQL requests
    GITHUB_API = 'https://api.github.com/graphql'

    # Get this many modules per request
    MODULES_PER_GRAPHQL = 50

    # The request we send to GitHub, with a parameter for the module specific section
    GRAPHQL_TEMPLATE = Template(read_text('netkan', 'downloads_query.graphql'))

    # The request string per module, depends on getDownloads fragment existing in
    # the main template
    MODULE_TEMPLATE = Template(
        '${ident}: repository(owner: "${user}", name: "${repo}") { ...getDownloads }')

    def __init__(self, github_token: str) -> None:
        self.netkan_dls: Dict[str, NetkanDownloads] = {}
        self.github_token = github_token
        logging.info('Starting new GraphQL query')

    def empty(self) -> bool:
        return len(self.netkan_dls) == 0

    def full(self) -> bool:
        return len(self.netkan_dls) >= self.MODULES_PER_GRAPHQL

    def add(self, nk_dl: NetkanDownloads) -> None:
        logging.info('Adding %s to GraphQL query', nk_dl.identifier)
        self.netkan_dls[nk_dl.identifier] = nk_dl

    def get_query(self) -> str:
        return self.GRAPHQL_TEMPLATE.safe_substitute(module_queries="\n".join(
            filter(None, [self.get_module_query(nk)
                          for nk in self.netkan_dls.values()])))

    def get_module_query(self, nk_dl: NetkanDownloads) -> Optional[str]:
        if nk_dl.kref_id:
            match = NetkanDownloads.GITHUB_PATTERN.match(nk_dl.kref_id)
            if match:
                (user, repo) = match.groups()
                return self.MODULE_TEMPLATE.safe_substitute(
                    ident=self.graphql_safe_identifier(nk_dl),
                    user=user, repo=repo)
        return None

    @staticmethod
    def graphql_safe_identifier(nk_dl: NetkanDownloads) -> str:
        """
        Identifiers can start with numbers and include hyphens.
        GraphQL doesn't like that, so we put an 'x' on the front
        and replace dashes with underscores (which luckily CAN'T
        appear in identifiers, so this is reversible).
        """
        return f'x{nk_dl.identifier.replace("-", "_")}'

    @staticmethod
    def from_graphql_safe_identifier(fake_ident: str) -> str:
        """
        Inverse of the above. Strip off the first character and
        replace underscores with dashes, to get back to the original
        identifier.
        """
        return fake_ident[1:].replace("_", "-")

    def get_result(self, counts: Optional[Dict[str, int]]) -> Dict[str, int]:
        logging.info('Running GraphQL query')
        if not counts:
            counts = {}
        full_query = self.get_query()
        result = self.graphql_to_github(full_query)
        for fake_ident, apidata in result['data'].items():
            if apidata:
                real_ident = self.from_graphql_safe_identifier(fake_ident)
                count = self.sum_graphql_result(apidata)
                logging.info('Count for %s is %s', real_ident, count)
                counts[real_ident] = count
        return counts

    def graphql_to_github(self, query: str) -> Dict[str, Any]:
        logging.info('Contacting GitHub')
        return requests.post(self.GITHUB_API, headers={
            'Authorization': f'bearer {self.github_token}'
        }, json={'query': query}).json()

    def sum_graphql_result(self, apidata: Dict[str, Any]) -> int:
        total = 0
        if apidata.get('parent', None):
            total += self.sum_graphql_result(apidata['parent'])
        for release in apidata['releases']['nodes']:
            for asset in release['releaseAssets']['nodes']:
                total += asset['downloadCount']
        return total


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
        graph_query = GraphQLQuery(self.github_token)
        for netkan in self.nk_repo.all_nk_paths():
            netkan_dl = NetkanDownloads(netkan, self.github_token)
            if netkan_dl.kref_src == 'github':
                # Process GitHub modules together in big batches
                graph_query.add(netkan_dl)
                if graph_query.full():
                    # Run the query
                    graph_query.get_result(self.counts)
                    # Start over with fresh query
                    graph_query = GraphQLQuery(self.github_token)
            else:
                count = netkan_dl.get_count()
                if count > 0:
                    logging.info('Count for %s is %s', netkan_dl.identifier, count)
                    self.counts[netkan_dl.identifier] = count
        if not graph_query.empty():
            # Final pass doesn't overflow the bound
            graph_query.get_result(self.counts)

    def write_json(self) -> None:
        self.output_file.write_text(
            json.dumps(self.counts, sort_keys=True, indent=4)
        )

    def commit_counts(self) -> None:
        self.ckm_repo.commit(
            [self.output_file.as_posix()],
            'NetKAN Updating Download Counts'
        )
        logging.info('Download counts changed and committed')
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
