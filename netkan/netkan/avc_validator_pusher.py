import logging
import os
import re
from pathlib import Path
import shutil
import requests
import git
import github

from .metadata import Netkan
from .status import ModStatus
from .github_pr import GitHubPR

# With apologies to Curtis Mayfield
class AVCValidatorPusher:

    WORKFLOW_URL = 'https://github.com/DasSkelett/AVC-VersionFileValidator/raw/master/examples/standard.yml'
    WORKFLOW_FOLDER = Path('.github/workflows')
    WORKFLOW_FILE = Path('AVC-VersionFileValidator.yml')
    WORKFLOW_PATH = Path(WORKFLOW_FOLDER, WORKFLOW_FILE)
    GITHUB_URL_PATTERN = re.compile('^https://github.com/([^/]+)/([^/]+)')
    BRANCH_NAME = 'add-avc-validator'
    MODS_ROOT = Path('/tmp/netkan-avc-mods')

    def __init__(self, netkan_repo, github_token):
        self.netkan_repo = netkan_repo
        self.github_token = github_token
        self.github = github.Github(github_token)

    def send_to_repos(self):
        self._download_file(self.WORKFLOW_URL, self.WORKFLOW_FILE)
        if not self.MODS_ROOT.exists():
            os.makedirs(self.MODS_ROOT)
        for repo_url in self._repositories():
            logging.info('Trying %s', repo_url)
            (user, repo) = self.GITHUB_URL_PATTERN.match(repo_url).groups()
            mod_path = Path(self.MODS_ROOT, f'{user}-{repo}')
            if mod_path.exists():
                logging.info('Already handled %s/%s', user, repo)
                self._cleanup_folder(mod_path)
                continue
            mod_repo = self._setup_repo(repo, self.github.get_user(), user, mod_path)
            if Path(mod_path, self.WORKFLOW_PATH).exists():
                logging.info('%s/%s already has the validator', user, repo)
                self._cleanup_folder(mod_path)
                continue
            version_files = list(mod_path.glob('**/*.version'))
            if len(version_files) == 0:
                logging.info('%s/%s has no version files', user, repo)
                self._cleanup_folder(mod_path)
                continue
            self._checkout_branch(mod_repo, self.BRANCH_NAME)
            os.makedirs(Path(mod_path, self.WORKFLOW_FOLDER))
            shutil.copyfile(self.WORKFLOW_FILE, Path(mod_path, self.WORKFLOW_PATH))
            mod_repo.index.add([self.WORKFLOW_PATH.as_posix()])
            mod_repo.index.commit('Add AVC Validator')
            self._submit_pr(mod_repo, self.BRANCH_NAME, repo, user)
            self._cleanup_folder(mod_path)

    def _download_file(self, url, path):
        open(path, 'wb').write(requests.get(url).content)

    def _cleanup_folder(self, path):
        shutil.rmtree(path)
        os.mkdir(path)

    def _netkans(self):
        return (Netkan(f) for f in sorted(Path(self.netkan_repo.working_dir).glob('**/*.netkan'),
                                          key=lambda p: p.stem.casefold()))

    def _repositories(self):
        """
        Return the repository URLs for all modules with vrefs.
        We could check for github $krefs, but that would miss mods on
        SpaceDock with the repository set.
        """
        return filter(None.__ne__,
                      (self._get_repository(nk)
                       for nk in self._netkans() if nk.has_vref))

    def _get_repository(self, netkan):
        """
        Return the repository string for the given identifier.
        Uses ModStatus because it includes SpaceDock.
        """
        try:
            status = ModStatus.get(netkan.identifier)
            # return status?.resources?.repository
            if status:
                resources = getattr(status, 'resources', None)
                if resources:
                    return getattr(resources, 'repository', None)
        except Exception:
            pass
        if netkan.on_github:
            logging.info('Falling back to %s', netkan.kref_id)
            return f'https://github.com/{netkan.kref_id}'
        return None

    def _setup_repo(self, repo_name, origin_user, upstream_user, path):
        self._create_fork(repo_name, upstream_user)
        logging.info('Cloning %s/%s', origin_user.login, repo_name)
        repo = git.Repo.clone_from(
            self._get_remote(repo_name, origin_user.login),
            path,
            branch='master')
        repo.create_remote('upstream', url=self._get_remote(repo_name, upstream_user))
        return repo

    def _create_fork(self, repo, user):
        logging.info('Forking %s/%s...', user, repo)
        return self.github.get_user().create_fork(
            self.github.get_user(user).get_repo(repo)
        )

    def _get_remote(self, repo, user):
        return f'git@github.com:{user}/{repo}.git'

    def _checkout_branch(self, mod_repo, name):
        try:
            mod_repo.remotes.origin.fetch(name)
        except git.GitCommandError:
            logging.info('Unable to fetch %s', name)

        (getattr(mod_repo.heads, name, None)
         or mod_repo.create_head(name)).checkout()

    def _submit_pr(self, mod_repo, branch_name, repo, user):
        logging.info('Submitting pull request')
        mod_repo.remotes.origin.push(f'{branch_name}:{branch_name}')
        # Each PR goes to a different repo, so we can't re-use this object
        GitHubPR(self.github_token, repo, user).create_pull_request(
            branch=branch_name,
            title='Add AVC Validator',
            body=(
                f'Greetings esteemed KSP mod author @{user}! '
                '\n\n'
                'KSP-AVC version files are a great tool for indicating '
                'version compatibility information, '
                'but they use JSON syntax, which can be tricky to '
                'maintain manually. '
                'Syntax errors like missing quotes, missing commas, '
                'and extra commas are common and can block a release '
                'from being added to CKAN. '
                '\n\n'
                'To help with this problem, the CKAN team has created '
                'a validation tool for version files. '
                'This pull request will allow GitHub to validate your '
                'version files when you make changes. '
                '\n\n'
                'Here is an example run to show what it looks like: '
                '\n\n'
                'https://github.com/HebaruSan/Astrogator/commit/60cd8c74b72bc0436e4f7a5a0cb7e7ec67887c20/checks?check_suite_id=361514587'
                '\n\n'
                'If this looks useful to you, Merge this PR to activate it. '
                'Otherwise just close it and we\'ll try not to bother you. '
                '\n\n'
                'See KSP-CKAN/NetKAN-Infra#113 for more information. '
            )
        )
