from hashlib import md5
import json
from typing import Tuple, Dict, Any, TYPE_CHECKING
from flask import Blueprint, current_app, request

from ..common import sqs_batch_entries
from .config import current_config

if TYPE_CHECKING:
    from mypy_boto3_sqs.type_defs import SendMessageBatchRequestEntryTypeDef
else:
    SendMessageBatchRequestEntryTypeDef = object

spacedock_add = Blueprint(
    'spacedock_add', __name__)  # pylint: disable=invalid-name


# For mod creation hook on SpaceDock, creates pull requests
# Handles: https://netkan.ksp-ckan.space/sd/add
# POST form parameters:
#     name:              Mod Name Entered by the User on spacedock
#     id:                12345
#     license:           GPL-3.0
#     username:          modauthor1
#     email:             modauthor1@gmail.com
#     short_description: A mod that you should definitely install
#     description:       A mod that you should definitely install, and so on and so on
#     external_link:     https://forum.kerbalspaceprogram.com/index.php?/topic/999999-ThreadTitle
#     source_link:       https://github.com/user/repo
#     user_url:          https://spacedock.info/profile/ModAuthor1
#     mod_url:           https://spacedock.info/mod/12345
#     site_name:         SpaceDock
@spacedock_add.route('/add', methods=['POST'], defaults={'game_id': 'ksp'})
@spacedock_add.route('/add/<game_id>', methods=['POST'])
def add_hook(game_id: str) -> Tuple[str, int]:
    # Submit add requests to queue in batches of <=10
    messages = [batch_message(request.form, game_id)]
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(f'Queueing add request batch: {batch}')
        current_config.client.send_message_batch(
            QueueUrl=current_config.add_queue.url,
            Entries=batch
        )
    return '', 204


def batch_message(raw: Dict[str, Any], game_id: str) -> SendMessageBatchRequestEntryTypeDef:
    body = json.dumps(raw)
    return {
        'Id':                     '1',
        'MessageBody':            body,
        'MessageGroupId':         '1',
        'MessageDeduplicationId': md5(body.encode()).hexdigest(),
        'MessageAttributes': {
            'GameId': {
                'DataType': 'String',
                'StringValue': game_id,
            }
        }
    }
