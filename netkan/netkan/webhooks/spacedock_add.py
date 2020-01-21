from hashlib import md5
import json
from flask import Blueprint, current_app, request

from ..common import sqs_batch_entries


spacedock_add = Blueprint('spacedock_add', __name__)  # pylint: disable=invalid-name


# For mod creation hook on SpaceDock, creates pull requests
# Handles: https://netkan.ksp-ckan.space/sd/add
# POST json input:
#   {
#     "name":              "Mod Name Entered by the User on SpaceDock",
#     "id":                "12345",
#     "license":           "GPL-3.0",
#     "username":          "ModAuthor1",
#     "email":             "modauthor1@gmail.com",
#     "short_description": "A mod that you should definitely install",
#     "description":       "A mod that you should definitely install, and so on and so on",
#     "external_link":     "https://forum.kerbalspaceprogram.com/index.php?/topic/999999-ThreadTitle",
#     "user_url":          "https://spacedock.info/profile/ModAuthor1",
#     "mod_url":           "https://spacedock.info/mod/12345",
#     "site_name":         "SpaceDock"
#   }
@spacedock_add.route('/add', methods=['POST'])
def add_hook():
    raw = request.get_json(silent=True)

    # Submit add requests to queue in batches of <=10
    messages = [batch_message(raw)]
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(f'Queueing add request batch: {batch}')
        current_app.config['client'].send_message_batch(
            QueueUrl=current_app.config['add_queue'].url,
            Entries=batch
        )
    return '', 204


def batch_message(raw):
    body = json.dumps(raw)
    return {
        'Id':                     '1',
        'MessageBody':            body,
        'MessageGroupId':         '1',
        'MessageDeduplicationId': md5(body.encode()).hexdigest()
    }
