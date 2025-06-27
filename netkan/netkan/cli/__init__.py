import click

from .services import (
    indexer,
    scheduler,
    spacedock_adder,
    mirrorer,
)
from .utilities import (
    auto_freezer,
    dump_status,
    export_status_s3,
    restore_status,
    recover_status_timestamps,
    redeploy_service,
    clean_cache,
    download_counter,
    ticket_closer,
    mirror_purge_epochs,
    analyze_mod,
    inflate_netkan,
)


@click.group()
def netkan() -> None:
    pass


netkan.add_command(indexer)
netkan.add_command(scheduler)
netkan.add_command(dump_status)
netkan.add_command(export_status_s3)
netkan.add_command(restore_status)
netkan.add_command(recover_status_timestamps)
netkan.add_command(redeploy_service)
netkan.add_command(clean_cache)
netkan.add_command(download_counter)
netkan.add_command(ticket_closer)
netkan.add_command(auto_freezer)
netkan.add_command(spacedock_adder)
netkan.add_command(mirrorer)
netkan.add_command(mirror_purge_epochs)
netkan.add_command(analyze_mod)
netkan.add_command(inflate_netkan)
