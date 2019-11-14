import json
import click

from ..status import ModStatus


@click.command()
def dump_status():
    click.echo(json.dumps(ModStatus.export_all_mods()))
