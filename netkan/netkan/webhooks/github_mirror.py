import re
from pathlib import Path
from hashlib import md5
from flask import Blueprint, current_app, request, jsonify

from .github_utils import signature_required
from ..common import sqs_batch_entries


github_mirror = Blueprint('github_mirror', __name__)  # pylint: disable=invalid-name


# For after-commit hook in CKAN-meta repo
# Handles: https://netkan.ksp-ckan.space/gh/mirror
@github_mirror.route('/mirror', methods=['POST'])
@signature_required
def mirror_hook():
    raw = request.get_json(silent=True)
    ref = raw.get('ref')
    expected_ref = current_app.config['ckm_repo'].git_repo.heads.master.path
    if ref != expected_ref:
        current_app.logger.info(
            "Wrong branch. Expected '%s', got '%s'", expected_ref, ref)
        return jsonify({'message': 'Wrong branch'}), 200
    commits = raw.get('commits')
    if not commits:
        current_app.logger.info('No commits received')
        return jsonify({'message': 'No commits received'}), 200
    # Make sure it's not from the crawler
    sender = raw.get('sender')
    if sender:
        login = sender.get('login')
        if login:
            if login == 'kspckan-crawler':
                current_app.logger.info('Commits sent by crawler, skipping on demand mirror')
                return '', 204
    # Submit mirroring requests to queue in batches of <=10
    messages = (batch_message(p) for p in paths_from_commits(commits))
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(f'Queueing mirroring request batch: {batch}')
        current_app.config['client'].send_message_batch(
            QueueUrl=current_app.config['mirror_queue'].url,
            Entries=batch
        )
    return '', 204


forbidden_id_chars = re.compile('[^-_A-Za-z0-9]')  # pylint: disable=invalid-name


def batch_message(path):
    body = path.as_posix()
    return {
        'Id':                     forbidden_id_chars.sub('_', body)[0:80],
        'MessageBody':            body,
        'MessageGroupId':         '1',
        'MessageDeduplicationId': md5(body.encode()).hexdigest()
    }


def ends_with_ckan(filename):
    return filename.endswith('.ckan')


def paths_from_commits(commits):
    files = set()
    for commit in commits:
        files |= set(filter(ends_with_ckan,
                            commit.get('added', []) + commit.get('modified', [])))
    return (Path(f) for f in files)
