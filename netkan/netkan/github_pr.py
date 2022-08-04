import logging
from typing import Optional, List, Dict, Any
from github import Github, GithubException

from .common import USER_AGENT


class GitHubPR:

    def __init__(self, token: str, repo: str, user: str) -> None:
        self.repo = Github(token, user_agent=USER_AGENT).get_repo(f'{user}/{repo}')

    def create_pull_request(self, title: str, branch: str, body: str, labels: Optional[List[str]] = None) -> None:
        try:
            pull = self.repo.create_pull(title, body, 'master', branch)
            logging.info('Pull request for %s opened at %s', branch, pull.html_url)

            if labels:
                # Labels have to be set separately
                pull.set_labels(*labels)

        except GithubException as exc:
            logging.error('Pull request for %s failed: %s',
                          branch, self.get_error_message(exc.data))

    @staticmethod
    def get_error_message(exc_data: Dict[str, Any]) -> str:
        return ' - '.join([exc_data.get('message',
                                        'Unknown error'),
                           *(err['message']
                             for err in exc_data.get('errors', [])
                             if 'message' in err)])
