import logging
from datetime import datetime, timedelta, timezone
from importlib.resources import read_text
from collections import defaultdict
from string import Template
import github

from .common import USER_AGENT


class TicketCloser:

    REPO_NAMES = ['CKAN', 'NetKAN']
    BODY_TEMPLATE = Template(read_text('netkan', 'ticket_close_template.md'))

    def __init__(self, token: str, user_name: str) -> None:
        self._gh = github.Github(token, user_agent=USER_AGENT)
        self._user_name = user_name

    def close_tickets(self, days_limit: int = 7) -> None:
        date_cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit)

        for repo_name in self.REPO_NAMES:
            repo = self._gh.get_repo(f'{self._user_name}/{repo_name}')
            issues = repo.get_issues(state='open',
                                     labels=[repo.get_label('support')],
                                     assignee='none')

            for issue in issues:

                if issue.comments < 1:
                    logging.info('Skipped (no comments): %s (%s#%s)',
                                 issue.title, repo_name, issue.number)
                    continue

                # Skip if last comment is by OP
                # get_comments()[-1] throws an exception
                last_comment = issue.get_comments().reversed[0]
                if last_comment.user.login == issue.user.login:
                    logging.info('Skipped (author comment): %s (%s#%s)',
                                 issue.title, repo_name, issue.number)
                    continue

                if issue.updated_at > date_cutoff:
                    logging.info('Skipped (recent update): %s (%s#%s)',
                                 issue.title, repo_name, issue.number)
                    continue

                logging.info('Closing: %s (%s#%s)',
                             issue.title, repo_name, issue.number)

                issue.create_comment(self.BODY_TEMPLATE.safe_substitute(defaultdict(lambda: '', {})))
                issue.edit(state='closed')
