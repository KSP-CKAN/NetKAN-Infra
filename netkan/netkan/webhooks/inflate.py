from typing import Tuple
from flask import Blueprint, current_app, request

from ..common import netkans, sqs_batch_entries, pull_all
from .config import current_config


inflate = Blueprint('inflate', __name__)  # pylint: disable=invalid-name


# For SpaceDock's trigger when new versions are uploaded
# Handles: https://netkan.ksp-ckan.space/inflate
# Payload: { "identifiers": [ "Id1", "Id2", ... ] }
@inflate.route('/inflate', methods=['POST'])
def inflate_hook() -> Tuple[str, int]:
    # SpaceDock doesn't set the `Content-Type: application/json` header
    raw = request.get_json(force=True)
    ids = raw.get('identifiers')  # type: ignore[union-attr]
    if not ids:
        current_app.logger.info('No identifiers received')
        return 'An array of identifiers is required', 400
    # Make sure our NetKAN and CKAN-meta repos are up to date
    pull_all(current_config.repos)
    messages = (nk.sqs_message(current_config.ckm_repo.highest_version(nk.identifier))
                for nk in netkans(current_config.nk_repo.git_repo.working_dir, ids))
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(f'Queueing inflation request batch: {batch}')
        current_config.client.send_message_batch(
            QueueUrl=current_config.inflation_queue.url,
            Entries=batch
        )
    return '', 204
