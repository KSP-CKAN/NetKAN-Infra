import logging
import datetime
import github


class TicketCloser:

    def __init__(self, token):
        self._gh = github.Github(token)

    def close_tickets(self, days_limit=7):
        date_cutoff = datetime.datetime.now() - datetime.timedelta(days=days_limit)

        for repo_name in ['CKAN', 'NetKAN']:
            repo = self._gh.get_repo(f'KSP-CKAN/{repo_name}')
            issues = repo.get_issues(
                state='open', labels=[repo.get_label('support')], assignee='none')

            for issue in issues:

                if issue.comments < 1:
                    logging.info(
                        'Skipped (no comments): %s (%s#%s)',
                        issue.title, repo_name, issue.number)
                    continue

                # Skip if last comment is by OP
                # get_comments()[-1] throws an exception
                last_comment = issue.get_comments().reversed[0]
                if last_comment.user.login == issue.user.login:
                    logging.info(
                        'Skipped (author comment): %s (%s#%s)',
                        issue.title, repo_name, issue.number)
                    continue

                if issue.updated_at > date_cutoff:
                    logging.info(
                        'Skipped (recent update): %s (%s#%s)',
                        issue.title, repo_name, issue.number)
                    continue

                logging.info(
                    'Closing: %s (%s#%s)',
                    issue.title, repo_name, issue.number)

                issue.create_comment("Hey there! I'm a fun-loving automated bot who's responsible for making sure old support tickets get closed out. As we haven't seen any activity on this ticket for a while, we're hoping the problem has been resolved and I'm closing out the ticket automatically. If I'm doing this in error, please add a comment to this ticket to let us know, and we'll re-open it!")

                issue.edit(state='closed')
