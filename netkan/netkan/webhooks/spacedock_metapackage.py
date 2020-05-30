from pathlib import Path
from flask import Blueprint, current_app, request, jsonify
from typing import Tuple, Iterable, Dict, Any, List

from ..common import pull_all
from ..metadata import Netkan
from ..repos import NetkanRepo


spacedock_metapackage = Blueprint('spacedock_metapackage', __name__)  # pylint: disable=invalid-name


# For metapackage hook on SpaceDock
# Handles: https://netkan.ksp-ckan.space/sd/metapackage
# POST form parameters:
#     mod_ids:     The mods' ID numbers on SpaceDock
@spacedock_metapackage.route('/metapackage', methods=['POST'])
def metapackage_hook() -> Tuple[str, int]:
    # Make sure our NetKAN and CKAN-meta repos are up to date
    pull_all(current_app.config['repos'])
    # Get the relevant netkans
    sd_ids = request.form.getlist('mod_ids')
    nks = find_netkans(current_app.config['nk_repo'], sd_ids)
    if nks:
        return jsonify({
            'missing': not_found(sd_ids, nks),
            'metapackage': mk_metapackage(nks, request.form.get('name', ''), request.form.get('abstract', '')),
        }), 204
    return 'No such modules', 404


def mk_metapackage(netkans: Iterable[Netkan], name: str, abstract: str) -> Dict[str, Any]:
    return {
        'spec_version': 'v1.4',
        'identifier': 'spacedock_metapackage',
        'name': name,
        'abstract': abstract,
        'kind': 'metapackage',
        'version': '1.0',
        'license': 'unknown',
        'depends': [{'name': nk.identifier} for nk in netkans]
    }


def find_netkans(nk_repo: NetkanRepo, sd_ids: List[str]) -> List[Netkan]:
    return [nk for nk in nk_repo.netkans()
            if nk.kref_src == 'spacedock' and nk.kref_id in sd_ids]


def not_found(sd_ids: Iterable[str], netkans: List[Netkan]) -> List[str]:
    nk_ids = {nk.kref_id for nk in netkans}
    return [i for i in sd_ids if i not in nk_ids]
