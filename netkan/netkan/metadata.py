import json
import re
from pathlib import Path
from hashlib import md5


class Netkan:

    kref_pattern = re.compile('^#/ckan/([^/]+)/(.+)$')

    def __init__(self, filename=None, contents=None):
        if filename:
            self.filename = Path(filename)
            self.contents = self.filename.read_text()
        else:
            self.contents = contents
        self._raw = json.loads(self.contents)

    def __getattr__(self, name):
        # Extract kref_src + kref_id from the kref
        if name in ['kref_src', 'kref_id']:
            self.kref_src, self.kref_id = self.kref_pattern.match(self.kref).groups()
            return getattr(self, name)

        # Return kref host, ie `self.on_spacedock`. Current krefs include
        # github, spacedock, curse and netkan.
        if name.startswith('on_'):
            return self._on_kref_src(name.split('_')[1])

        # Make kref/vref access more pythonic
        if name in ['kref', 'vref']:
            if self._raw.get(f'${name}'):
                return self._raw.get(f'${name}')

        # Access netkan dictionary as attributes
        if name in self._raw:
            return self._raw[name]

        raise AttributeError

    def _on_kref_src(self, kref_src):
        if getattr(self, 'kref', False):
            return kref_src == self.kref_src
        return False

    @property
    def has_kref(self):
        return hasattr(self, 'kref')

    @property
    def has_vref(self):
        return hasattr(self, 'vref')

    def hook_only(self):
        if self.has_vref:
            return False
        return self.on_spacedock

    def sqs_message(self):
        return {
            'Id': self.filename.stem,
            'MessageBody': self.contents,
            'MessageGroupId': '1',
            'MessageDeduplicationId': md5(self.contents.encode()).hexdigest()
        }
