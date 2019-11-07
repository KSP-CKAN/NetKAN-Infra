from pathlib import Path
from flask import Blueprint, current_app, request

from ..metadata import Netkan
from ..common import sqs_batch_entries


spacedock_inflate = Blueprint('spacedock_inflate', __name__)  # pylint: disable=invalid-name


# For after-upload hook on SpaceDock
# Handles: https://netkan.ksp-ckan.space/sd/inflate
# POST form parameters: mod_id=1234&event_type=update
@spacedock_inflate.route('/inflate', methods=['POST'])
def inflate_hook():
    # Make sure our NetKAN repo is up to date
    current_app.config['netkan_repo'].remotes.origin.pull('master', strategy_option='theirs')
    # Get the relevant netkans
    nks = find_netkans(request.form.get('mod_id'))
    if nks:
        # Submit them to the queue
        messages = (nk.sqs_message() for nk in nks)
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
