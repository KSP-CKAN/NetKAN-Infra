import json
import requests


# We don't need a whole lot out of github, consuming a library
# and learning how it worked seemed like a waste.
class GitHubPR:

    def __init__(self, token, repo, user):
        self.token = token
        self.repo = repo
        self.user = user

    def create_pull_request(self, title, branch, body):
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
                self.repo, self.user
            ),
            headers=headers,
            data=json.dumps(data),
        )
        if response.status_code not in [200, 201, 204]:
            return (False, 'PR for {} failed: {}'.format(
                branch,
                response.json()['errors'][0]['message']
            ))
        pr = response.json()
        return (True, 'PR for {} opened at {}'.format(
            branch, pr['html_url']
        ))
