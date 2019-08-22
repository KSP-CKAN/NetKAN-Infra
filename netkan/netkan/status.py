import boto3
import json
import os
import time
from datetime import datetime
from dateutil.parser import parse
from pathlib import Path
from pynamodb.models import Model
from pynamodb.attributes import (
    UnicodeAttribute, UTCDateTimeAttribute, BooleanAttribute
)


# The click context isn't available during the setup of this object and the
# idea is that you'd specify a different table using a different class. Since
# this is for dev and dev won't have access to the production table taking a
# environment variable to override is acceptable for now.
def table_name():
    return os.getenv('STATUS_DB', 'NetKANStatus')


def region():
    return os.getenv('AWS_DEFAULT_REGION', 'us-west-2')


class ModStatus(Model):
    class Meta:
        table_name = table_name()
        region = region()

    ModIdentifier = UnicodeAttribute(hash_key=True)
    last_error = UnicodeAttribute(null=True)
    last_checked = UTCDateTimeAttribute(null=True)
    last_indexed = UTCDateTimeAttribute(null=True)
    last_inflated = UTCDateTimeAttribute(null=True)
    success = BooleanAttribute()

    def mod_attrs(self):
        attributes = {}
        for key in self.get_attributes().keys():
            if key == 'ModIdentifier':
                continue
            attributes[key] = getattr(self, key, None)
            if isinstance(attributes[key], datetime):
                attributes[key] = attributes[key].isoformat()
        return attributes

    # If we ever have more than 1MB of Status in the DB we'll need paginate,
    # however our current status sits at < 300Kb with all the fields populated.
    # So we'd probably need to be tracking 10,000+ mods before it becomes
    # a problem.
    @classmethod
    def export_all_mods(cls, compat=True):
        data = {}
        for mod in cls.scan(rate_limit=5):
            data[mod.ModIdentifier] = mod.mod_attrs()

            # Persist compability with existing status ui
            if compat:
                failed = False if mod.success else True
                data[mod.ModIdentifier]['failed'] = failed
                data[mod.ModIdentifier].pop('success')

        return data

    @classmethod
    def export_to_s3(cls, bucket, key, compat=True):
        client = boto3.client('s3')
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(cls.export_all_mods(compat)).encode(),
        )

    # This likely isn't super effecient, but we really should only have to use
    # this operation once to seed the existing history.
    @classmethod
    def restore_status(cls, filename):
        existing = json.loads(Path(filename).read_text())
        with cls.batch_write() as batch:
            for key, item in existing.items():
                for item_key in ['checked', 'indexed', 'inflated']:
                    update_key = 'last_{}'.format(item_key)
                    if not item[update_key]:
                        continue
                    item[update_key] = parse(
                        item.pop(update_key)
                    )
                item['ModIdentifier'] = key
                item['success'] = False if item['failed'] else True
                item.pop('failed')

                # Every batch write consumes a credit, we want to leave spare
                # credits available for other operations and also not error out
                # during the operation (pynamodb doesn't seem to have a limit
                # option on batch queries).
                if len(batch.pending_operations) == 5:
                    batch.commit()
                    time.sleep(1)

                batch.save(ModStatus(**item))
