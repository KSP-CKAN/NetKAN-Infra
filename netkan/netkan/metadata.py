import json
import re
from functools import total_ordering
from pathlib import Path
from hashlib import sha1
import uuid


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
        if self.has_kref:
            self.kref_src, self.kref_id = self.KREF_PATTERN.match(self.kref).groups()
        else:
            self.kref_src = None
            self.kref_id = None

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

    def sqs_message_attribs(self, ckan_group=None):
        attribs = {}
        if ckan_group and not getattr(self, 'x_netkan_allow_out_of_order', False):
            attribs['HighestVersion'] = ckan_group.highest_version().string
        return attribs

    def sqs_message(self, ckan_group=None):
        return {
            'Id': self.identifier,
            'MessageBody': self.contents,
            'MessageGroupId': '1',
            'MessageDeduplicationId': uuid.uuid4().hex,
            'MessageAttributes': self.sqs_message_attribs(ckan_group),
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
    def version(self):
        if self._raw.get('version'):
            return self.Version(self._raw.get('version'))

    @property
    def cache_prefix(self):
        if 'download' not in self._raw:
            return None
        return sha1(self.download.encode()).hexdigest().upper()[0:8]

    @property
    def cache_filename(self):
        if not {'download', 'identifier', 'version', 'download_content_type'} <= self._raw.keys():
            return None
        return '{}-{}-{}.{}'.format(
            self.cache_prefix,
            self.identifier,
            self.version.string.replace(':', '-'),
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

    @total_ordering
    class Version:

        PATTERN = re.compile("^(?:(?P<epoch>[0-9]+):)?(?P<version>.*)$")

        def __init__(self, version_string):
            self.string = version_string
            match = self.PATTERN.fullmatch(self.string)
            if not match:
                raise Exception('Invalid version format')
            if match.group('epoch') and match.group('epoch').isnumeric():
                self.epoch = int(match.group('epoch'))
            else:
                # https://github.com/KSP-CKAN/CKAN/blob/master/Spec.md#epoch
                # 0 assumed if no epoch supplied
                self.epoch = 0
            self.bare_version = match.group('version')
            if self.bare_version is None:
                raise Exception

        # @total_ordering doesn't generate this one right. Maybe it compares the strings?
        def __eq__(self, other):
            return not self > other and not other > self

        # The CKAN-Core implementation relies on a __cmp__-like concept. __cmp__ has been deprecated in Python3.
        # The logic has been adjusted a bit to be run as __gt__. All the other possible relation comparisons
        # (except __eq__) are deduced from it by @total_ordering.
        def __gt__(self, other):

            def _string_compare(v1, v2) -> (int, str, str):
                _result: int
                _first_remainder = ''
                _second_remainder = ''

                # Our starting assumptions are, that both versions are completely strings,
                # with no remainder. We'll then check if they're not.
                str1 = v1
                str2 = v2

                # Start by walking along our version string until we find a number,
                # thereby finding the starting string in both cases. If we fall off
                # the end, then our assumptions made above hold.
                for i in range(0, len(v1)):
                    if v1[i].isdigit():
                        _first_remainder = v1[i:]
                        str1 = v1[:i]
                        break

                for i in range(0, len(v2)):
                    if v2[i].isdigit():
                        _second_remainder = v2[i:]
                        str2 = v2[:i]
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
                        _result = ((str1 > str2)-(str1 < str2))
                else:
                    _result = ((str1 > str2)-(str1 < str2))

                return _result, _first_remainder, _second_remainder

            def _number_compare(v1, v2) -> (int, str, str):
                _result: int
                _first_remainder = ''
                _second_remainder = ''

                minimum_length1 = 0
                for i in range(0, len(v1)):
                    if not v1[i].isdigit():
                        _first_remainder = v1[i:]
                        break
                    minimum_length1 += 1

                minimum_length2 = 0
                for i in range(0, len(v2)):
                    if not v2[i].isdigit():
                        _second_remainder = v2[i:]
                        break
                    minimum_length2 += 1

                if v1[:minimum_length1].isnumeric():
                    integer1 = int(v1[:minimum_length1])
                else:
                    integer1 = 0

                if v2[:minimum_length2].isnumeric():
                    integer2 = int(v2[:minimum_length2])
                else:
                    integer2 = 0

                _result = ((integer1 > integer2)-(integer1 < integer2))
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

        def __str__(self):
            return self.string


class CkanGroup:

    """
    Represents all Ckans from CKAN-meta associated with a particular identifier.
    Allows us to calculate things about the group, such as the highest module version.
    """

    def __init__(self, ckan_meta_path, identifier):
        self.path = Path(ckan_meta_path, identifier)

    def highest_version(self):
        ckans = (Ckan(p) for p in self.path.glob('**/*.ckan'))
        highest = max(ckans, default=None, key=lambda ck: ck.version)
        if highest:
            return highest.version
        return None
