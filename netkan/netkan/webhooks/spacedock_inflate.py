from pathlib import Path
from flask import Blueprint, current_app, request
from typing import Tuple, Iterable, List

from ..common import sqs_batch_entries, pull_all
from ..metadata import Netkan
from .config import current_config


spacedock_inflate = Blueprint('spacedock_inflate', __name__)  # pylint: disable=invalid-name


# For after-upload hook on SpaceDock
# Handles: https://netkan.ksp-ckan.space/sd/inflate
# POST form parameters:
#     mod_id:     The mod's ID number on SpaceDock
#     event_type: update         - New version of mod was uploaded
#                 version-update - Default version changed
#                 delete         - Mod was deleted from SpaceDock
@spacedock_inflate.route('/inflate', methods=['POST'])
def inflate_hook() -> Tuple[str, int]:
    # Make sure our NetKAN and CKAN-meta repos are up to date
    pull_all(current_config.repos)
    # Get the relevant netkans
    nks = find_netkans(request.form.get('mod_id', ''))
    if nks:
        if request.form.get('event_type') == 'delete':
            # Just let the team know on Discord
            nk_msg = ', '.join(nk.identifier for nk in nks)
            current_app.logger.error(
                f'A SpaceDock mod has been deleted, affected netkans: {nk_msg}')
            return '', 204
        elif request.form.get('event_type') == 'locked':
            # Just let the team know on Discord
            nk_msg = ', '.join(nk.identifier for nk in nks)
            current_app.logger.error(
                f'A SpaceDock mod has been locked, affected netkans: {nk_msg}')
            return '', 204
        elif request.form.get('event_type') == 'unlocked':
            # Just let the team know on Discord
            nk_msg = ', '.join(nk.identifier for nk in nks)
            current_app.logger.error(
                f'A SpaceDock mod has been unlocked again, affected netkans: {nk_msg}')
            return '', 204
        else:
            # Submit them to the queue
            messages = (nk.sqs_message(current_config.ckm_repo.highest_version(nk.identifier))
                        for nk in nks)
            for batch in sqs_batch_entries(messages):
                current_config.client.send_message_batch(
                    QueueUrl=current_config.inflation_queue.url,
                    Entries=batch
                )
            return '', 204
    return 'No such module', 404


def find_netkans(sd_id: str) -> List[Netkan]:
    all_nk = current_config.nk_repo.netkans()
    return [nk for nk in all_nk if nk.kref_src == 'spacedock' and nk.kref_id == sd_id]
