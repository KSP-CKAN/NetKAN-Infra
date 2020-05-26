from pathlib import Path
from flask import Blueprint, current_app, request, jsonify

from ..common import netkans, sqs_batch_entries, pull_all
from .github_utils import signature_required


github_inflate = Blueprint('github_inflate', __name__)  # pylint: disable=invalid-name


# For after-commit hook in NetKAN repo
# Handles: https://netkan.ksp-ckan.space/gh/inflate
@github_inflate.route('/inflate', methods=['POST'])
@signature_required
def inflate_hook():
    raw = request.get_json(silent=True)
    branch = raw.get('ref')
    if branch != current_app.config['nk_repo'].git_repo.head.ref.path:
        current_app.logger.info('Received inflation request for wrong ref %s, ignoring', branch)
        return jsonify({'message': 'Wrong branch'}), 200
    commits = raw.get('commits')
    if not commits:
        current_app.logger.info('No commits received')
        return jsonify({'message': 'No commits received'}), 200
    inflate(ids_from_commits(commits))
    return '', 204


# For release hook in module repo
# Handles: https://netkan.ksp-ckan.space/gh/release?identifier=AwesomeMod
# Putting this here instead of in a github_release.py file
# because it's small and quite similar to inflate
@github_inflate.route('/release', methods=['POST'])
@signature_required
def release_hook():
    ident = request.args.get('identifier')
    if not ident:
        return 'Param "identifier" is required, e.g. http://netkan.ksp-ckan.space/gh/release?identifier=AwesomeMod', 400
    inflate([ident])
    return '', 204


def ends_with_netkan(filename):
    return filename.endswith('.netkan')


def ids_from_commits(commits):
    files = set()
    for commit in commits:
        files |= set(filter(ends_with_netkan,
                            commit.get('added', []) + commit.get('modified', [])))
    return (Path(f).stem for f in files)


def inflate(ids):
    # Make sure our NetKAN and CKAN-meta repos are up to date
    pull_all(current_app.config['repos'])
    messages = (nk.sqs_message(current_app.config['ckm_repo'].group(nk.identifier))
                for nk in netkans(current_app.config['nk_repo'].git_repo.working_dir, ids))
    for batch in sqs_batch_entries(messages):
        current_app.config['client'].send_message_batch(
            QueueUrl=current_app.config['inflation_queue'].url,
            Entries=batch
        )
