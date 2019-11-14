import click

from ..ticket_closer import TicketCloser


@click.command()
@click.option(
    '--token', required=True, envvar='GH_Token',
    help='GitHub token for querying and closing issues',
)
@click.option(
    '--days-limit', default=7,
    help='Number of days to wait for OP to reply',
)
def ticket_closer(token, days_limit):
    TicketCloser(token).close_tickets(days_limit)
