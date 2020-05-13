from pathlib import Path
from flask import Blueprint, current_app, request

from ..common import sqs_batch_entries, pull_all
from ..metadata import Netkan, CkanGroup


spacedock_inflate = Blueprint('spacedock_inflate', __name__)  # pylint: disable=invalid-name


# For after-upload hook on SpaceDock
# Handles: https://netkan.ksp-ckan.space/sd/inflate
# POST form parameters:
#     mod_id:     The mod's ID number on SpaceDock
#     event_type: update         - New version of mod was uploaded
#                 version-update - Default version changed
#                 delete         - Mod was deleted from SpaceDock
@spacedock_inflate.route('/inflate', methods=['POST'])
def inflate_hook():
    # Make sure our NetKAN and CKAN-meta repos are up to date
    pull_all(current_app.config['repos'])
    # Get the relevant netkans
    nks = find_netkans(request.form.get('mod_id'))
    if nks:
        if request.form.get('event_type') == 'delete':
            # Just let the team know on Discord
            nk_msg = ', '.join(nk.identifier for nk in nks)
            current_app.logger.error(
                f'A SpaceDock mod has been deleted, affected netkans: {nk_msg}')
            return '', 204
        else:
            # Submit them to the queue
            messages = (nk.sqs_message(CkanGroup(current_app.config['ckanmeta_repo'].working_dir, nk.identifier))
                        for nk in nks)
            for batch in sqs_batch_entries(messages):
                current_app.config['client'].send_message_batch(
                    QueueUrl=current_app.config['inflation_queue'].url,
                    Entries=batch
                )
            return '', 204
    return 'No such module', 404


def find_netkans(sd_id):
    nk_path = Path(current_app.config['netkan_repo'].working_dir, 'NetKAN')
    all_nk = (Netkan(nk) for nk in nk_path.glob('**/*.netkan'))
    return (nk for nk in all_nk if nk.kref_src == 'spacedock' and nk.kref_id == sd_id)
