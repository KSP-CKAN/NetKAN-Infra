import json
import requests
import logging


# We don't need a whole lot out of github, consuming a library
# and learning how it worked seemed like a waste.
class GitHubPR:

    def __init__(self, token: str, repo: str, user: str) -> None:
        self.token = token
        self.repo = repo
        self.user = user

    def create_pull_request(self, title: str, branch: str, body: str) -> None:
        headers = {
            'Authorization': 'token {}'.format(self.token),
            'Content-Type': 'application/json'
        }
        data = {
            'title': title,
            'base': 'master',
            'head': branch,
            'body': body,
        }
        response = requests.post(
            'https://api.github.com/repos/{}/{}/pulls'.format(
                self.user, self.repo
            ),
            headers=headers,
            data=json.dumps(data),
        )
        if response.status_code not in [200, 201, 204]:
            error = ''
            message = response.json()['message']
            try:
                error = response.json()['errors'][0]['message']
            except KeyError:
                pass
            logging.info('PR for {} failed: {} - {}'.format(
                branch,
                message,
                error
            ))
            return
        pr = response.json()
        logging.info('PR for {} opened at {}'.format(
            branch, pr['html_url']
        ))
