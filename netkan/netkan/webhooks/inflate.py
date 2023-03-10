from typing import Tuple
from flask import Blueprint, current_app, request

from ..common import netkans, sqs_batch_entries, pull_all
from .config import current_config


inflate = Blueprint('inflate', __name__)  # pylint: disable=invalid-name


# For SpaceDock's trigger when new versions are uploaded
# Handles: https://netkan.ksp-ckan.space/inflate
# Payload: { "identifiers": [ "Id1", "Id2", ... ] }
@inflate.route('/inflate', methods=['POST'], defaults={'game_id': 'ksp'})
@inflate.route('/inflate/<game_id>', methods=['POST'])
def inflate_hook(game_id: str) -> Tuple[str, int]:
    # SpaceDock doesn't set the `Content-Type: application/json` header
    raw = request.get_json(force=True)
    game = current_config.common.game(game_id)
    ids = raw.get('identifiers')  # type: ignore[union-attr]
    if not ids:
        current_app.logger.info('No identifiers received')
        return 'An array of identifiers is required', 400
    # Make sure our NetKAN and CKAN-meta repos are up to date
    pull_all(game.repos)
    messages = (nk.sqs_message(game.ckanmeta_repo.highest_version(nk.identifier))
                for nk in netkans(str(game.netkan_repo.git_repo.working_dir), ids, game_id=game_id))
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(
            f'Queueing inflation request batch: {batch}')
        current_config.client.send_message_batch(
            QueueUrl=current_config.inflation_queue(game_id).url,
            Entries=batch
        )
    return '', 204
