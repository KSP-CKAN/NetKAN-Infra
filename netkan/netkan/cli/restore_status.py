import click

from ..status import ModStatus


@click.command()
@click.argument('filename')
def restore_status(filename):
    click.echo(
        'To keep within free tier rate limits, this could take some time'
    )
    ModStatus.restore_status(filename)
    click.echo('Done!')
