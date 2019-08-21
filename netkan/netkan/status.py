import boto3
import json
from pynamodb.models import Model
from datetime import datetime
from pynamodb.attributes import (
    UnicodeAttribute, UTCDateTimeAttribute, BooleanAttribute
)


# TODO: Set table_name from click context
class ModStatus(Model):
    class Meta:
        table_name = 'DevNetKANStatus'
        region = 'us-west-2'

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
    def export_all_mods(self):
        data = {}
        for mod in self.scan(rate_limit=5):
            data[mod.ModIdentifier] = mod.mod_attrs()
        return data

    def export_to_s3(self, bucket, key):
        client = boto3.client('s3')
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(self.export_all_mods()).encode(),
        )
