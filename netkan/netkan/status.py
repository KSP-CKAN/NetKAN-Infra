import json
import logging
import os
import time
from datetime import datetime, timezone
from itertools import chain
from pathlib import Path
from typing import Optional, Dict, Any
from dateutil.parser import parse
from pynamodb.models import Model
from pynamodb.expressions.condition import Condition
from pynamodb.attributes import (
    UnicodeAttribute, UTCDateTimeAttribute, BooleanAttribute, MapAttribute
)
import boto3
from git import Repo

from .repos import CkanMetaRepo

# The click context isn't available during the setup of this object and the
# idea is that you'd specify a different table using a different class. Since
# this is for dev and dev won't have access to the production table taking a
# environment variable to override is acceptable for now.


def table_name() -> str:
    return os.getenv('STATUS_DB', 'MultiKANStatus')


def region() -> str:
    return os.getenv('AWS_DEFAULT_REGION', 'us-west-2')


class ModStatus(Model):
    class Meta:
        table_name = table_name()
        region = region()

    ModIdentifier = UnicodeAttribute(hash_key=True)
    game_id = UnicodeAttribute(range_key=True)
    last_error = UnicodeAttribute(null=True)
    last_warnings = UnicodeAttribute(null=True)
    last_checked = UTCDateTimeAttribute(null=True)
    last_indexed = UTCDateTimeAttribute(null=True)
    last_inflated = UTCDateTimeAttribute(null=True)
    last_downloaded = UTCDateTimeAttribute(null=True)
    release_date = UTCDateTimeAttribute(null=True)
    success = BooleanAttribute()
    frozen = BooleanAttribute(default=False)
    resources: 'MapAttribute[str, Any]' = MapAttribute(default={})

    def mod_attrs(self) -> Dict[str, Any]:
        attributes = {}
        for key in self.get_attributes().keys():
            if key == 'ModIdentifier':
                continue
            attr = getattr(self, key, None)
            attributes[key] = (
                attr.isoformat() if attr and isinstance(attr, datetime)
                else attr.as_dict() if attr and isinstance(attr, MapAttribute)
                else attr
            )
        return attributes

    # If we ever have more than 1MB of Status in the DB we'll need paginate,
    # however our current status sits at < 300Kb with all the fields populated.
    # So we'd probably need to be tracking 10,000+ mods before it becomes
    # a problem.
    @classmethod
    def export_game_mods(cls, condition: Condition, compat: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for mod in cls.scan(rate_limit=5, filter_condition=condition):
            data[mod.ModIdentifier] = mod.mod_attrs()

            # Persist compability with existing status ui
            if compat:
                failed = not mod.success
                data[mod.ModIdentifier]['failed'] = failed
                data[mod.ModIdentifier].pop('success')

        return data

    @classmethod
    def export_all_mods(cls, compat: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for game_id in ['ksp', 'ksp2']:
            data.update({game_id: cls.export_game_mods(
                condition=ModStatus.game_id == game_id, compat=compat)})
        data.update({'no_game_id': cls.export_game_mods(
            condition=ModStatus.game_id.does_not_exist(), compat=compat)})
        return data

    @classmethod
    def export_to_s3(cls, bucket: str, key: str, game_id: str, compat: bool = True) -> None:
        client = boto3.client('s3')
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(cls.export_game_mods(
                condition=ModStatus.game_id == game_id, compat=compat)).encode(),
        )
        logging.info('Exported to s3://%s/%s', bucket, key)

    @staticmethod
    def normalise_item(identifier: str, values: Dict[str, Any]) -> None:
        # Ensure all date/time items are passed to ModStatus
        # as proper datetime.datetime obects
        for item_key in ['checked', 'indexed', 'inflated', 'downloaded']:
            update_key = f'last_{item_key}'
            if not values[update_key]:
                continue
            values[update_key] = parse(
                values.pop(update_key)
            )
        if values['release_date'] is not None:
            values['release_date'] = parse(values.pop('release_date'))

        values['ModIdentifier'] = identifier
        values['success'] = not values['failed']
        # Assist in migration of tables to multi-game
        if values['game_id'] is None:
            values['game_id'] = 'ksp'
        values.pop('failed')

    # This likely isn't super effecient, but we really should only have to use
    # this operation once to seed/migrate the existing history.
    @classmethod
    def restore_status(cls, filename: str) -> None:
        existing = json.loads(Path(filename).read_text(encoding='UTF-8'))
        with cls.batch_write() as batch:
            for game in chain(existing.values()):
                for key, item in game.items():
                    # Every batch write consumes a credit, we want to leave spare
                    # credits available for other operations and also not error out
                    # during the operation (pynamodb doesn't seem to have a limit
                    # option on batch queries).
                    if len(batch.pending_operations) == 5:
                        batch.commit()
                        time.sleep(1)
                    cls.normalise_item(key, item)
                    batch.save(ModStatus(**item))

    @classmethod
    def last_indexed_from_git(cls, ckanmeta_repo: Repo, identifier: str) -> Optional[datetime]:
        try:
            return parse(ckanmeta_repo.git.log('--', identifier, format='%aI', max_count=1).split("\n")[0]).astimezone(timezone.utc)
        except Exception as exc:  # pylint: disable=broad-except
            logging.error('Unable to recover last_indexed for %s',
                          identifier, exc_info=exc)
            return None

    @classmethod
    def recover_timestamps(cls, ckm_repo: CkanMetaRepo) -> None:
        with cls.batch_write() as batch:
            logging.info('Recovering timestamps...')
            for mod in cls.scan(rate_limit=5):
                if not mod.last_indexed:
                    logging.info('Looking up timestamp for %s', mod.ModIdentifier)
                    mod.last_indexed = cls.last_indexed_from_git(
                        ckm_repo.git_repo, mod.ModIdentifier)
                    if mod.last_indexed:
                        logging.info('Saving %s: %s', mod.ModIdentifier, mod.last_indexed)
                        batch.save(mod)
            logging.info('Done!')
