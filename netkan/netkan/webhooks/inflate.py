from flask import Blueprint, current_app, request

from ..common import netkans, sqs_batch_entries


inflate = Blueprint('inflate', __name__)  # pylint: disable=invalid-name


# For SpaceDock's trigger when new versions are uploaded
# Handles: https://netkan.ksp-ckan.space/inflate
# Payload: { "identifiers": [ "Id1", "Id2", ... ] }
@inflate.route('/inflate', methods=['POST'])
def inflate_hook():
    # SpaceDock doesn't set the `Content-Type: application/json` header
    ids = request.get_json(force=True).get('identifiers')
    if not ids:
        current_app.logger.info('No identifiers received')
        return 'An array of identifiers is required', 400
    # Make sure our NetKAN repo is up to date
    current_app.config['netkan_repo'].remotes.origin.pull('master', strategy_option='theirs')
    messages = (nk.sqs_message()
                for nk in netkans(current_app.config['netkan_repo'].working_dir, ids))
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(f'Queueing inflation request batch: {batch}')
        current_app.config['client'].send_message_batch(
            QueueUrl=current_app.config['inflation_queue'].url,
            Entries=batch
        )
    return '', 204
