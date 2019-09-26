import json
import re
from pathlib import Path
from hashlib import md5


class Netkan:

    kref_pattern = re.compile('^#/ckan/([^/]+)/(.+)$')

    def __init__(self, filename):
        self.filename = Path(filename)
        self.contents = self.filename.read_text()
        self._raw = json.loads(self.contents)

    def __getattr__(self, name):
        # Extract kind + mod_id from the kref
        if name in ['kind', 'mod_id']:
            self.kind, self.mod_id = self.kref_pattern.match(self.kref).groups()
            return getattr(self, name)

        # Return kref host, ie `self.on_spacedock`. Current krefs include
        # github, spacedock, curse and netkan.
        if name.startswith('on_'):
            return self._on_kind(name.split('_')[1])

        # Make kref/vref access more pythonic
        if name in ['kref', 'vref']:
            if self._raw.get(f'${name}'):
                return self._raw.get(f'${name}')

        # Access netkan dictionary as attributes
        if name in self._raw:
            return self._raw[name]

        raise AttributeError

    def _on_kind(self, kind):
        if getattr(self, 'kref', False):
            return kind == self.kind
        return False

    def hook_only(self):
        if hasattr(self, 'vref'):
            return False
        return self.on_spacedock

    def sqs_message(self):
        return {
            'Id': self.filename.stem,
            'MessageBody': self.contents,
            'MessageGroupId': '1',
            'MessageDeduplicationId': md5(self.contents.encode()).hexdigest()
        }
