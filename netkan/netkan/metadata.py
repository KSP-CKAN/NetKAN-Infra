import json
import re
from pathlib import Path
from hashlib import md5, sha1


class Netkan:

    KREF_PATTERN = re.compile('^#/ckan/([^/]+)/(.+)$')

    def __init__(self, filename=None, contents=None):
        if filename:
            self.filename = Path(filename)
            self.contents = self.filename.read_text()
        else:
            self.contents = contents
        self._raw = json.loads(self.contents)
        # Extract kref_src + kref_id from the kref
        self.kref_src, self.kref_id = self.KREF_PATTERN.match(
            self.kref).groups()

    def __getattr__(self, name):
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


class Ckan:

    MIME_TO_EXTENSION = {
        'application/x-gzip':           'gz',
        'application/x-tar':            'tar',
        'application/x-compressed-tar': 'tar.gz',
        'application/zip':              'zip',
    }

    def __init__(self, filename=None, contents=None):
        if filename:
            self.filename = Path(filename)
            self.contents = self.filename.read_text()
        else:
            self.contents = contents
        self._raw = json.loads(self.contents)

    def __getattr__(self, name):
        if name in self._raw:
            return self._raw[name]
        if name == 'kind':
            return self._raw.get('kind', 'package')
        raise AttributeError

    @property
    def cache_prefix(self):
        if not 'download' in self._raw:
            return None
        return sha1(self.download.encode()).hexdigest().upper()[0:8]

    @property
    def cache_filename(self):
        if not {'download', 'identifier', 'version', 'download_content_type'} <= self._raw.keys():
            return None
        return '{}-{}-{}.{}'.format(
            self.cache_prefix,
            self.identifier,
            self.version.replace(':', '-'),
            self.MIME_TO_EXTENSION[self.download_content_type],
        )

    def authors(self):
        auth = self.author
        if isinstance(auth, list):
            return auth
        else:
            return [auth]

    def licenses(self):
        lic = self.license
        if isinstance(lic, list):
            return lic
        else:
            return [lic]
