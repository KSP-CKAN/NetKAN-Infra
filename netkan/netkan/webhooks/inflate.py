from flask import Blueprint, current_app, request

from .common import netkans, sqs_batch_entries


inflate = Blueprint('inflate', __name__)


# For SpaceDock's trigger when new versions are uploaded
# Handles: https://netkan.ksp-ckan.space/inflate
# Payload: { "identifiers": [ "Id1", "Id2", ... ] }
@inflate.route('/inflate', methods=['POST'])
def inflate_hook():
    ids = request.json.get('identifiers')
    if not ids:
        current_app.logger.info('No identifiers received')
        return 'An array of identifiers is required', 400
    messages = (nk.sqs_message()
                for nk in netkans(current_app.config['netkan_repo'].working_dir, ids))
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(f'Queueing inflation request batch: {batch}')
        current_app.config['client'].send_message_batch(
            QueueUrl=current_app.config['inflation_queue'].url,
            Entries=batch
        )
    return '', 204
