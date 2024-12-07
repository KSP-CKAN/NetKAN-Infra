import json
import re
from functools import total_ordering
from pathlib import Path
from hashlib import sha1
import uuid
import urllib.parse
from string import Template
from typing import Optional, List, Tuple, Union, Any, Dict, TYPE_CHECKING
from ruamel.yaml import YAML
import dateutil.parser

from .csharp_compat import csharp_uri_tostring

if TYPE_CHECKING:
    from mypy_boto3_sqs.type_defs import SendMessageBatchRequestEntryTypeDef
else:
    SendMessageBatchRequestEntryTypeDef = object


class Netkan:

    KREF_PATTERN = re.compile('^#/ckan/([^/]+)/(.+)$')

    def __init__(
        self,
        filename: Optional[Union[str, Path]] = None,
        contents: Optional[str] = None,
        game_id: Optional[str] = None,
    ) -> None:
        if filename:
            self.filename = Path(filename)
            self.contents = self.filename.read_text(encoding='UTF-8')
        elif contents:
            self.contents = contents
        self.game_id = game_id
        yaml = YAML(typ='safe')
        # YAML parser doesn't allow tabs, so replace with spaces
        self._raw = next(yaml.load_all(self.contents.replace('\t', '    ')))
        # Extract kref_src + kref_id from the kref
        self.kref_src: Optional[str]
        self.kref_id: Optional[str]
        if self.has_kref:
            match = self.KREF_PATTERN.match(self.kref)
            if match:
                self.kref_src, self.kref_id = match.groups()
        else:
            self.kref_src = None
            self.kref_id = None

    def __repr__(self) -> str:
        try:
            return f'<{self.__class__.__name__}({self.identifier})>'
        except AttributeError:
            return f'<{self.__class__.__name__}(identifier undefined)>'

    def __getattr__(self, name: str) -> Any:
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

    def _on_kref_src(self, kref_src: str) -> bool:
        if getattr(self, 'kref', False):
            return kref_src == self.kref_src
        return False

    @property
    def has_kref(self) -> bool:
        return hasattr(self, 'kref')

    @property
    def has_vref(self) -> bool:
        return hasattr(self, 'vref')

    def hook_only(self) -> bool:
        if self.has_vref:
            return False
        return self.on_spacedock

    @staticmethod
    def string_attrib(val: str) -> Dict[str, str]:
        return {
            'DataType': 'String',
            'StringValue': val,
        }

    def sqs_message_attribs(self, high_ver: Optional['Ckan.Version'] = None, high_ver_pre: Optional['Ckan.Version'] = None) -> Dict[str, Any]:
        attribs: Dict[str, Any] = {
            'GameId': self.string_attrib(self.game_id or 'ksp')
        }
        if high_ver and not getattr(self, 'x_netkan_allow_out_of_order', False):
            attribs['HighestVersion'] = self.string_attrib(high_ver.string)
        if high_ver_pre and not getattr(self, 'x_netkan_allow_out_of_order', False):
            attribs['HighestVersionPrerelease'] = self.string_attrib(high_ver_pre.string)
        return attribs

    def sqs_message(
            self, high_ver: Optional['Ckan.Version'] = None, high_ver_pre: Optional['Ckan.Version'] = None) -> SendMessageBatchRequestEntryTypeDef:
        hex_id = uuid.uuid4().hex
        return {
            'Id': hex_id,
            'MessageBody': self.contents,
            'MessageGroupId': '1',
            'MessageDeduplicationId': hex_id,
            'MessageAttributes': self.sqs_message_attribs(high_ver, high_ver_pre),
        }


class Ckan:

    EPOCH_VERSION_REGEXP = re.compile('^[0-9]+:')

    BUCKET_EXCLUDE_PATTERN = re.compile(r'^[^a-zA-Z0-9]+|[^a-zA-Z0-9._-]')

    REDISTRIBUTABLE_LICENSES = {
        "public-domain",
        "Apache", "Apache-1.0", "Apache-2.0",
        "Artistic", "Artistic-1.0", "Artistic-2.0",
        "BSD-2-clause", "BSD-3-clause", "BSD-4-clause",
        "ISC",
        "CC-BY", "CC-BY-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0",
        "CC-BY-SA", "CC-BY-SA-1.0", "CC-BY-SA-2.0", "CC-BY-SA-2.5", "CC-BY-SA-3.0", "CC-BY-SA-4.0",
        "CC-BY-NC", "CC-BY-NC-1.0", "CC-BY-NC-2.0", "CC-BY-NC-2.5", "CC-BY-NC-3.0", "CC-BY-NC-4.0",
        "CC-BY-NC-SA", "CC-BY-NC-SA-1.0", "CC-BY-NC-SA-2.0", "CC-BY-NC-SA-2.5", "CC-BY-NC-SA-3.0", "CC-BY-NC-SA-4.0",
        "CC-BY-NC-ND", "CC-BY-NC-ND-1.0", "CC-BY-NC-ND-2.0", "CC-BY-NC-ND-2.5", "CC-BY-NC-ND-3.0", "CC-BY-NC-ND-4.0",
        "CC-BY-ND", "CC-BY-ND-1.0", "CC-BY-ND-2.0", "CC-BY-ND-2.5", "CC-BY-ND-3.0", "CC-BY-ND-4.0",
        "CC0",
        "CDDL", "CPL",
        "EFL-1.0", "EFL-2.0",
        "Expat", "MIT",
        "GPL-1.0", "GPL-2.0", "GPL-3.0",
        "LGPL-2.0", "LGPL-2.1", "LGPL-3.0",
        "GFDL-1.0", "GFDL-1.1", "GFDL-1.2", "GFDL-1.3",
        "GFDL-NIV-1.0", "GFDL-NIV-1.1", "GFDL-NIV-1.2", "GFDL-NIV-1.3",
        "LPPL-1.0", "LPPL-1.1", "LPPL-1.2", "LPPL-1.3c",
        "MPL-1.1", "MPL-2.0",
        "Perl",
        "Python-2.0",
        "QPL-1.0",
        "W3C",
        "Zlib",
        "Zope",
        "WTFPL",
        "Unlicense",
        "open-source", "unrestricted"
    }

    @total_ordering
    class Version:

        PATTERN = re.compile("^(?:(?P<epoch>[0-9]+):)?(?P<version>.*)$")

        def __init__(self, version_string: str) -> None:
            self.string = version_string
            match = self.PATTERN.fullmatch(self.string)
            if not match:
                raise ValueError('Invalid version format')
            if match.group('epoch') and match.group('epoch').isnumeric():
                self.epoch = int(match.group('epoch'))
            else:
                # https://github.com/KSP-CKAN/CKAN/blob/master/Spec.md#epoch
                # 0 assumed if no epoch supplied
                self.epoch = 0
            self.bare_version = match.group('version')
            if self.bare_version is None:
                raise ValueError

        # @total_ordering doesn't generate this one right. Maybe it compares the strings?
        def __eq__(self, other: object) -> bool:
            if isinstance(other, self.__class__):
                return not self > other and not other > self
            return False

        # The CKAN-Core implementation relies on a __cmp__-like concept. __cmp__ has been deprecated in Python3.
        # The logic has been adjusted a bit to be run as __gt__. All the other possible relation comparisons
        # (except __eq__) are deduced from it by @total_ordering.
        def __gt__(self, other: 'Ckan.Version') -> bool:

            def _string_compare(ver1: str, ver2: str) -> Tuple[int, str, str]:
                _result: int
                _first_remainder = ''
                _second_remainder = ''

                # Our starting assumptions are, that both versions are completely strings,
                # with no remainder. We'll then check if they're not.
                str1 = ver1
                str2 = ver2

                # Start by walking along our version string until we find a number,
                # thereby finding the starting string in both cases. If we fall off
                # the end, then our assumptions made above hold.
                for i, piece in enumerate(ver1):
                    if piece.isdigit():
                        _first_remainder = ver1[i:]
                        str1 = ver1[:i]
                        break

                for i, piece in enumerate(ver2):
                    if piece.isdigit():
                        _second_remainder = ver2[i:]
                        str2 = ver2[:i]
                        break

                # Then compare the two strings, and return our comparison state.
                # Override sorting of '.' to higher than other characters.
                if len(str1) > 0 and len(str2) > 0:
                    if str1[0] != '.' and str2[0] == '.':
                        _result = -1
                    elif str1[0] == '.' and str2[0] != '.':
                        _result = 1
                    elif str1[0] == '.' and str2[0] == '.':
                        if len(str1) == 1 and len(str2) > 1:
                            _result = 1
                        elif len(str1) > 1 and len(str2) == 1:
                            _result = -1
                        else:
                            _result = 0
                    else:
                        # Do an artificial __cmp__
                        _result = (str1 > str2) - (str1 < str2)
                else:
                    _result = (str1 > str2) - (str1 < str2)

                return _result, _first_remainder, _second_remainder

            def _number_compare(ver1: str, ver2: str) -> Tuple[int, str, str]:
                _result: int
                _first_remainder = ''
                _second_remainder = ''

                minimum_length1 = 0
                for i, piece in enumerate(ver1):
                    if not piece.isdigit():
                        _first_remainder = ver1[i:]
                        break
                    minimum_length1 += 1

                minimum_length2 = 0
                for i, piece in enumerate(ver2):
                    if not piece.isdigit():
                        _second_remainder = ver2[i:]
                        break
                    minimum_length2 += 1

                if ver1[:minimum_length1].isnumeric():
                    integer1 = int(ver1[:minimum_length1])
                else:
                    integer1 = 0

                if ver2[:minimum_length2].isnumeric():
                    integer2 = int(ver2[:minimum_length2])
                else:
                    integer2 = 0

                _result = (integer1 > integer2) - (integer1 < integer2)
                return _result, _first_remainder, _second_remainder

            # Here begins the main comparison logic
            if self is other:
                return False

            if other.epoch == self.epoch and other.bare_version == self.bare_version:
                return False

            # Compare epochs first
            if self.epoch != other.epoch:
                return self.epoch >= other.epoch

            # Epochs are the same. Do the dance described in
            # https://github.com/KSP-CKAN/CKAN/blob/master/Spec.md#version-ordering
            first_remainder = self.bare_version
            second_remainder = other.bare_version

            # Process our strings while there are characters remaining
            while len(first_remainder) > 0 and len(second_remainder) > 0:
                # Start by comparing the string parts.
                (result, first_remainder, second_remainder) = _string_compare(
                    first_remainder, second_remainder)

                if result != 0:
                    return result > 0

                # Otherwise, compare the number parts.
                # It's okay not to check if our strings are exhausted, because
                # if they are the exhausted parts will return zero.
                (result, first_remainder, second_remainder) = _number_compare(
                    first_remainder, second_remainder)

                # Again, return difference if found.
                if result != 0:
                    return result > 0

            # Oh, we've run out of one or both strings.
            if len(first_remainder) == 0:
                # If both remainders are empty, both versions are equal => gt is false.
                # Else, whichever version is empty first is the smallest. (1.2 < 1.2.3)
                return False
            return True

        def __str__(self) -> str:
            return self.string

    CACHE_PATH = Path.home().joinpath('ckan_cache')
    MIME_TO_EXTENSION = {
        'application/x-gzip': 'gz',
        'application/x-tar': 'tar',
        'application/x-compressed-tar': 'tar.gz',
        'application/zip': 'zip',
        'application/vnd.github+json': 'zip',
    }
    ISODATETIME_PROPERTIES = [
        'release_date'
    ]
    MIRROR_FILENAME_TEMPLATE = Template('$prefix-$identifier-$version.$extension')

    def __init__(self, filename: Optional[Union[str, Path]] = None, contents: Optional[str] = None) -> None:
        if filename:
            self.filename = Path(filename)
            self.contents = self.filename.read_text(encoding='UTF-8')
        elif contents:
            self.contents = contents
        self._raw = json.loads(self.contents, object_hook=self._custom_parser)

    def __repr__(self) -> str:
        try:
            return f'<{self.__class__.__name__}({self.identifier}, {self.version})>'
        except AttributeError:
            return f'<{self.__class__.__name__}(identifier or version undefined)>'

    def _custom_parser(self, dct: Dict[str, Any]) -> Dict[str, Any]:
        # Special handling for DateTime fields
        for k in self.ISODATETIME_PROPERTIES:
            if k in dct:
                try:
                    dct[k] = dateutil.parser.isoparse(dct[k])
                except:  # pylint: disable=bare-except  # noqa: E722
                    pass
        return dct

    def __getattr__(self, name: str) -> Any:
        if name in self._raw:
            return self._raw[name]
        if name == 'kind':
            return self._raw.get('kind', 'package')
        raise AttributeError

    @property
    def version(self) -> Version:
        raw_ver = self._raw.get('version')
        if not raw_ver:
            raise AttributeError('Required property `version` not found')
        return self.Version(raw_ver)

    # download can be a list now, default to the first one
    @property
    def download(self) -> str:
        download = self._raw.get('download')
        if isinstance(download, list):
            return download[0] if isinstance(download[0], str) and len(download) > 0 else ''
        return download

    # Provide all downloads with alternate property in case we need them,
    # including implicit archive.org fallback where applicable
    @property
    def downloads(self) -> List[str]:
        download = self._raw['download']
        downloads = download if isinstance(download, list) else [download]
        archive = self.mirror_download() if self.redistributable else None
        return [*downloads, archive] if archive else downloads

    @property
    def cache_prefix(self) -> Optional[str]:
        if 'download' not in self._raw:
            return None
        return sha1(csharp_uri_tostring(self.download).encode()).hexdigest()[0:8].upper()

    @property
    def cache_find_file(self) -> Optional[Path]:
        found = list(self.CACHE_PATH.glob(f'**/{self.cache_prefix}*.zip'))
        if found:
            return found[0]
        return None

    @property
    def cache_filename(self) -> Optional[str]:
        if not {'download', 'identifier', 'download_content_type'} <= self._raw.keys():
            return None
        if not self.version:
            return None
        return f'{self.cache_prefix}-{self.identifier}-{self.version.string.replace(":", "-")}.{self.MIME_TO_EXTENSION[self.download_content_type]}'

    def source_download(self, branch: str = 'master') -> Optional[str]:
        # self?.resources?.repository
        repository = getattr(self, 'resources', {}).get('repository', None)
        if repository:
            parsed = urllib.parse.urlparse(repository)
            # Strip extra trailing pieces from URL
            prefix = '/'.join(repository.split('/')[0:5])
            if parsed.netloc == 'github.com':
                # https://github.com/HebaruSan/Astrogator/archive/master.zip
                return f'{prefix}/archive/{branch}.zip'
            if parsed.netloc == 'bitbucket.org':
                # https://bitbucket.org/Taverius/b9-aerospace/get/master.zip
                return f'{prefix}/get/{branch}.zip'
            if parsed.netloc == 'gitlab.com':
                # https://gitlab.com/N70/Kerbalism/-/archive/master/Kerbalism-master.zip
                name = parsed.path.split('/')[2]
                return f'{prefix}/-/archive/{branch}/{name}-{branch}.zip'
            if parsed.netloc == 'git.srv.hoerberg.de':
                # https://git.srv.hoerberg.de/tom300z/4ksp/-/archive/master/4ksp-master.zip
                name = parsed.path.split('/')[2]
                return f'{prefix}/-/archive/{branch}/{name}-{branch}.zip'
        return None

    def authors(self) -> List[str]:
        auth = self.author
        return auth if isinstance(auth, list) else [auth]

    def licenses(self) -> List[str]:
        lic = self.license
        return lic if isinstance(lic, list) else [lic]

    @property
    def is_prerelease(self) -> bool:
        return self._raw.get('release_status') in ('testing', 'development')

    @property
    def redistributable(self) -> bool:
        for lic in self.licenses():
            if lic in self.REDISTRIBUTABLE_LICENSES:
                return True
        return False

    def mirror_filename(self, with_epoch: bool = True) -> Optional[str]:
        if 'download_hash' not in self._raw:
            return None
        return self.MIRROR_FILENAME_TEMPLATE.safe_substitute(
            prefix=self._mirror_prefix(),
            identifier=self.identifier,
            version=self._format_version(with_epoch),
            extension=Ckan.MIME_TO_EXTENSION[self.download_content_type])

    def mirror_download(self, with_epoch: bool = True) -> Optional[str]:
        filename = self.mirror_filename(with_epoch)
        if filename:
            return f'https://archive.org/download/{self.identifier}-{self._format_version(with_epoch)}/{filename}'
        return None

    def mirror_item(self, with_epoch: bool = True) -> str:
        return self._ia_bucket_sanitize(
            f'{self.identifier}-{self._format_version(with_epoch)}')

    def _mirror_prefix(self) -> str:
        return (self.download_hash['sha1']
                if 'sha1' in self.download_hash
                else self.download_hash['sha256']
               )[0:8]

    # InternetArchive says:
    # Bucket names should be valid archive identifiers;
    # try someting matching this regular expression:
    # ^[a-zA-Z0-9][a-zA-Z0-9_.-]{4,100}$
    # (We enforce everything except the minimum of 4 characters)
    @classmethod
    def _ia_bucket_sanitize(cls, s: str) -> str:
        return cls.BUCKET_EXCLUDE_PATTERN.sub('', s)[:100]

    def _format_version(self, with_epoch: bool) -> Optional[str]:
        if self.version:
            if with_epoch:
                return self.version.string.replace(' ', '_').replace(':', '-')
            return self.EPOCH_VERSION_REGEXP.sub('', self.version.string.replace(' ', '_'))
        return None
