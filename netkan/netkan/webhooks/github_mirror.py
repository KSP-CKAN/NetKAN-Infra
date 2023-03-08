import re
from pathlib import Path
from hashlib import md5
from typing import Tuple, List, Iterable, Dict, Any, Set, Union, TYPE_CHECKING
from flask import Blueprint, current_app, request, jsonify, Response

from .github_utils import signature_required
from ..common import sqs_batch_entries
from .config import current_config

if TYPE_CHECKING:
    from mypy_boto3_sqs.type_defs import SendMessageBatchRequestEntryTypeDef
else:
    SendMessageBatchRequestEntryTypeDef = object

github_mirror = Blueprint(
    'github_mirror', __name__)  # pylint: disable=invalid-name


# For after-commit hook in CKAN-meta repo
# Handles: https://netkan.ksp-ckan.space/gh/mirror
@github_mirror.route('/mirror', methods=['POST'], defaults={'game_id': 'ksp'})
@github_mirror.route('/mirror/<game_id>', methods=['POST'])
@signature_required
def mirror_hook(game_id: str) -> Tuple[Union[Response, str], int]:
    raw = request.get_json(silent=True)
    ref = raw.get('ref')  # type: ignore[union-attr]
    expected_ref = current_config.common.game(
        game_id).ckanmeta_repo.git_repo.heads.master.path
    if ref != expected_ref:
        current_app.logger.info(
            "Wrong branch. Expected '%s', got '%s'", expected_ref, ref)
        return jsonify({'message': 'Wrong branch'}), 200
    commits = raw.get('commits')  # type: ignore[union-attr]
    if not commits:
        current_app.logger.info('No commits received')
        return jsonify({'message': 'No commits received'}), 200
    # Submit mirroring requests to queue in batches of <=10
    messages = (batch_message(p, game_id) for p in paths_from_commits(commits))
    for batch in sqs_batch_entries(messages):
        current_app.logger.info(f'Queueing mirroring request batch: {batch}')
        current_config.client.send_message_batch(
            QueueUrl=current_config.mirror_queue.url,
            Entries=batch
        )
    return '', 204


forbidden_id_chars = re.compile(
    '[^-_A-Za-z0-9]')  # pylint: disable=invalid-name


def batch_message(path: Path, game_id: str) -> SendMessageBatchRequestEntryTypeDef:
    body = path.as_posix()
    return {
        'Id':                     forbidden_id_chars.sub('_', body)[-80:],
        'MessageBody':            body,
        'MessageGroupId':         '1',
        'MessageDeduplicationId': md5(body.encode()).hexdigest(),
        'MessageAttributes':   {
            'GameId': {
                'DataType': 'String',
                'StringValue': game_id,
            }
        }
    }


def ends_with_ckan(filename: str) -> bool:
    return filename.endswith('.ckan')


def paths_from_commits(commits: List[Dict[str, Any]]) -> Iterable[Path]:
    files: Set[str] = set()
    for commit in commits:
        files |= set(filter(ends_with_ckan,
                            commit.get('added', []) + commit.get('modified', [])))
    return (Path(f) for f in files)
