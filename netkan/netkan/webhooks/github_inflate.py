import logging
from pathlib import Path
from flask import Blueprint, current_app, request, jsonify
from typing import List, Tuple, Iterable, Dict, Any, Set

from ..common import netkans, sqs_batch_entries, pull_all
from ..metadata import Netkan
from ..status import ModStatus
from .github_utils import signature_required
from .config import current_config

github_inflate = Blueprint('github_inflate', __name__)  # pylint: disable=invalid-name


# For after-commit hook in NetKAN repo
# Handles: https://netkan.ksp-ckan.space/gh/inflate
@github_inflate.route('/inflate', methods=['POST'])
@signature_required
def inflate_hook() -> Tuple[str, int]:
    raw = request.get_json(silent=True)
    branch = raw.get('ref')
    if branch != current_config.nk_repo.git_repo.head.ref.path:
        current_app.logger.info('Received inflation request for wrong ref %s, ignoring', branch)
        return jsonify({'message': 'Wrong branch'}), 200
    commits = raw.get('commits')
    if not commits:
        current_app.logger.info('No commits received')
        return jsonify({'message': 'No commits received'}), 200
    inflate(ids_from_commits(commits))
    freeze(frozen_ids_from_commits(commits))
    return '', 204


# For release hook in module repo
# Handles: https://netkan.ksp-ckan.space/gh/release?identifier=AwesomeMod
# Putting this here instead of in a github_release.py file
# because it's small and quite similar to inflate
@github_inflate.route('/release', methods=['POST'])
@signature_required
def release_hook() -> Tuple[str, int]:
    ident = request.args.get('identifier')
    if not ident:
        return 'Param "identifier" is required, e.g. http://netkan.ksp-ckan.space/gh/release?identifier=AwesomeMod', 400
    inflate([ident])
    return '', 204


def ends_with_netkan(filename: str) -> bool:
    return filename.endswith(f".{current_config.nk_repo.UNFROZEN_SUFFIX}")


def ids_from_commits(commits: List[Dict[str, Any]]) -> Iterable[str]:
    files: Set[str] = set()
    for commit in commits:
        files |= set(filter(ends_with_netkan,
                            commit.get('added', []) + commit.get('modified', [])))
    return (Path(f).stem for f in files)


def inflate(ids: Iterable[str]) -> None:
    # Make sure our NetKAN and CKAN-meta repos are up to date
    pull_all(current_config.repos)
    messages = (nk.sqs_message(current_config.ckm_repo.highest_version(nk.identifier))
                for nk in netkans(current_config.nk_repo.git_repo.working_dir, ids))
    for batch in sqs_batch_entries(messages):
        current_config.client.send_message_batch(
            QueueUrl=current_config.inflation_queue.url,
            Entries=batch
        )


def ends_with_frozen(filename: str) -> bool:
    return filename.endswith(f".{current_config.nk_repo.FROZEN_SUFFIX}")


def frozen_ids_from_commits(commits: List[Dict[str, Any]]) -> List[str]:
    files: Set[str] = set()
    for commit in commits:
        files |= set(filter(ends_with_frozen,
                            commit.get('added', []) + commit.get('modified', [])))
    return [Path(f).stem for f in files]


def freeze(ids: List[str]) -> None:
    if ids:
        logging.info('Marking frozen mods...')
        for ident in ids:
            try:
                status = ModStatus.get(ident)
                if not status.frozen:
                    logging.info('Marking frozen: %s', ident)
                    # https://readthedocs.org/projects/pynamodb/downloads/pdf/stable/
                    status.update(actions=[ModStatus.frozen.set(True)])
            except ModStatus.DoesNotExist:
                # No status, don't need to freeze
                pass
        logging.info('Done!')
