import logging
from pathlib import Path
from typing import List, Tuple, Iterable, Dict, Any, Set, Union
from flask import Blueprint, current_app, request, jsonify, Response

from ..common import netkans, sqs_batch_entries, pull_all
from ..repos import NetkanRepo
from ..status import ModStatus
from .github_utils import signature_required
from .config import current_config

github_inflate = Blueprint(
    'github_inflate', __name__)  # pylint: disable=invalid-name


# For after-commit hook in NetKAN repo
# Handles: https://netkan.ksp-ckan.space/gh/inflate
@github_inflate.route('/inflate/<game_id>', methods=['POST'])
@signature_required
def inflate_hook(game_id: str) -> Tuple[Union[Response, str], int]:
    raw = request.get_json(silent=True)
    branch = raw.get('ref')  # type: ignore[union-attr]
    if branch != current_config.common.game(game_id).netkan_repo.git_repo.head.ref.path:
        current_app.logger.info(
            'Received inflation request for wrong ref %s, ignoring', branch)
        return jsonify({'message': 'Wrong branch'}), 200
    commits = raw.get('commits')  # type: ignore[union-attr]
    if not commits:
        current_app.logger.info('No commits received')
        return jsonify({'message': 'No commits received'}), 200
    inflate(ids_from_commits(commits), game_id)
    freeze(frozen_ids_from_commits(commits), game_id)
    return '', 204


# For release hook in module repo
# Handles: https://netkan.ksp-ckan.space/gh/release?identifier=AwesomeMod
# Putting this here instead of in a github_release.py file
# because it's small and quite similar to inflate
@github_inflate.route('/release/<game_id>', methods=['POST'])
@signature_required
def release_hook(game_id: str) -> Tuple[str, int]:
    ident = request.args.get('identifier')
    if not ident:
        return 'Param "identifier" is required, e.g. http://netkan.ksp-ckan.space/gh/release?identifier=AwesomeMod', 400
    inflate([ident], game_id)
    return '', 204


def ends_with_netkan(filename: str) -> bool:
    return filename.endswith(f".{NetkanRepo.UNFROZEN_SUFFIX}")


def ids_from_commits(commits: List[Dict[str, Any]]) -> Iterable[str]:
    files: Set[str] = set()
    for commit in commits:
        files |= set(filter(ends_with_netkan,
                            commit.get('added', []) + commit.get('modified', [])))
    return (Path(f).stem for f in files)


def inflate(ids: Iterable[str], game_id: str) -> None:
    game = current_config.common.game(game_id)
    if game.netkan_repo.git_repo.working_dir:
        # Make sure our NetKAN and CKAN-meta repos are up to date
        pull_all(game.repos)
        messages = (nk.sqs_message(game.ckanmeta_repo.highest_version(nk.identifier))
                    for nk in netkans(str(game.netkan_repo.git_repo.working_dir), ids, game_id))
        for batch in sqs_batch_entries(messages):
            current_config.client.send_message_batch(
                QueueUrl=current_config.inflation_queue(game_id).url,
                Entries=batch
            )


def ends_with_frozen(filename: str) -> bool:
    return filename.endswith(f".{NetkanRepo.FROZEN_SUFFIX}")


def frozen_ids_from_commits(commits: List[Dict[str, Any]]) -> List[str]:
    files: Set[str] = set()
    for commit in commits:
        files |= set(filter(ends_with_frozen,
                            commit.get('added', []) + commit.get('modified', [])))
    return [Path(f).stem for f in files]


def freeze(ids: List[str], game_id: str) -> None:
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
            # Delete cached downloads
            cached_downloads = list(filter(
                None,
                (ck.cache_find_file
                 for ck in current_config.common.game(game_id).ckanmeta_repo.ckans(ident))))
            if cached_downloads:
                logging.info('Purging %s files from cache for %s',
                             len(cached_downloads), ident)
                for download in cached_downloads:
                    download.unlink()
        logging.info('Done!')
