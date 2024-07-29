from hashlib import md5
import json
from typing import Tuple, TYPE_CHECKING
from flask import Blueprint, current_app, request
from werkzeug.datastructures import ImmutableMultiDict

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


def batch_message(raw: 'ImmutableMultiDict[str, str]', game_id: str) -> SendMessageBatchRequestEntryTypeDef:
    body = json.dumps({**raw,
                       # Turn the separate user property lists into a list of user dicts so JSON can encode it
                       # (the original properties will only have the first user)
                       'all_authors': [{'username':            user_tuple[0],
                                        'user_github':         user_tuple[1],
                                        'user_forum_id':       user_tuple[2],
                                        'user_forum_username': user_tuple[3],
                                        'email':               user_tuple[4]}
                                       for user_tuple
                                       in zip(raw.getlist('username'),
                                              raw.getlist('user_github'),
                                              raw.getlist('user_forum_id'),
                                              raw.getlist('user_forum_username'),
                                              raw.getlist('email'))]})
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
