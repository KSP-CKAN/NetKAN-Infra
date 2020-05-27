import os
import re
import tempfile
import urllib.request
import hashlib
import logging
import shutil
from pathlib import Path
import requests
import boto3
import internetarchive

from .metadata import Ckan


class Mirrorer:

    EPOCH_ID_REGEXP = re.compile('-[0-9]+-')
    EPOCH_TITLE_REGEXP = re.compile(' - [0-9]+:')

    def __init__(self, ckm_repo, ia_access, ia_secret, ia_collection):
        self.ckm_repo = ckm_repo
        self.ia_collection = ia_collection
        self.ia_access = ia_access
        self.ia_session = internetarchive.get_session(config={
            's3': {
                'access': ia_access,
                'secret': ia_secret,
            }
        })

    def process_queue(self, queue_name, timeout):
        queue = boto3.resource('sqs').get_queue_by_name(QueueName=queue_name)
        while True:
            messages = queue.receive_messages(
                MaxNumberOfMessages=10,
                MessageAttributeNames=['All'],
                VisibilityTimeout=timeout,
            )
            if messages:
                # Check if archive.org is overloaded
                if self.ia_overloaded():
                    logging.info('The Internet Archive is overloaded, try again later')
                    continue
                # Get up to date copy of the metadata for the files we're mirroring
                logging.info('Updating repo')
                self.ckm_repo.git_repo.heads.master.checkout()
                self.ckm_repo.git_repo.remotes.origin.pull('master', strategy_option='theirs')
                # Start processing the messages
                to_delete = []
                for msg in messages:
                    path = Path(self.ckm_repo.git_repo.working_dir, msg.body)
                    if self.try_mirror(CkanMirror(self.ia_collection, path)):
                        # Successfully handled -> OK to delete
                        to_delete.append(self.deletion_msg(msg))
                queue.delete_messages(Entries=to_delete)
                # Clean up GitPython's lingering file handles between batches
                self.ckm_repo.git_repo.close()

    def try_mirror(self, ckan):
        if not ckan.can_mirror:
            # If we can't mirror, then we're done with this message
            logging.info('Ckan %s cannot be mirrored', ckan.mirror_item())
            return True
        if ckan.mirrored(self.ia_session):
            # If it's already mirrored, then we're done with this message
            logging.info('Ckan %s is already mirrored', ckan.mirror_item())
            return True
        download_file = ckan.open_download()
        if ckan.download_hash.get('sha256') != self.large_file_sha256(download_file):
            # Bad download, try again later
            logging.info('Hash mismatch')
            return False
        logging.info('Uploading %s', ckan.mirror_item())
        item = internetarchive.Item(self.ia_session, ckan.mirror_item())
        item.upload_file(download_file.name, ckan.mirror_filename(),
                         ckan.item_metadata,
                         ckan.download_headers)
        source_url = ckan.source_download
        if source_url:
            with tempfile.NamedTemporaryFile() as tmp:
                logging.info('Attempting to archive source from %s', source_url)
                urllib.request.urlretrieve(source_url, tmp.name)
                item.upload_file(tmp.name, ckan.mirror_source_filename(),
                                 ckan.item_metadata,
                                 ckan.source_download_headers(tmp.name))
        return True

    @staticmethod
    def large_file_sha256(file, block_size=8192):
        sha = hashlib.sha256()
        for block in iter(lambda: file.read(block_size), b''):
            sha.update(block)
        return sha.hexdigest().upper()

    @staticmethod
    def deletion_msg(msg):
        return {
            'Id':            msg.message_id,
            'ReceiptHandle': msg.receipt_handle,
        }

    def ia_overloaded(self):
        return requests.get(
            'https://s3.us.archive.org/?check_limit=1&accesskey={}'.format(
                self.ia_access
            )
        ).status_code == 503

    def purge_epochs(self, dry_run):
        if dry_run:
            logging.info('Dry run mode enabled, no changes will be made')
        for result in self._epoch_search():
            ident = result.get('identifier')
            if ident:
                item = self.ia_session.get_item(ident)
                logging.info('Found epoch to purge: %s (%s)', ident, item.metadata.get('title'))
                if not dry_run:
                    item.modify_metadata({
                        'identifier': self.EPOCH_ID_REGEXP.sub('-', ident),
                        'title': self.EPOCH_TITLE_REGEXP.sub(' - ', item.metadata.get('title')),
                    })

    def _epoch_search(self):
        return filter(
            self._result_has_epoch,
            self.ia_session.search_items(
                f'collection:({self.ia_collection})',
                fields=['identifier', 'title']
            )
        )

    def _result_has_epoch(self, result):
        return self.EPOCH_TITLE_REGEXP.search(result.get('title'))


class CkanMirror(Ckan):

    REDISTRIBUTABLE_LICENSES = {
        "public-domain",
        "Apache", "Apache-1.0", "Apache-2.0",
        "Artistic", "Artistic-1.0", "Artistic-2.0",
        "BSD-2-clause", "BSD-3-clause", "BSD-4-clause",
        "ISC",
        "CC-BY", "CC-BY-1.0", "CC-BY-2.0", "CC-BY-2.5", "CC-BY-3.0", "CC-BY-4.0",
        "CC-BY-SA", "CC-BY-SA-1.0", "CC-BY-SA-2.0", "CC-BY-SA-2.5", "CC-BY-SA-3.0", "CC-BY-SA-4.0",
        "CC-BY-NC", "CC-BY-NC-1.0", "CC-BY-NC-2.0", "CC-BY-NC-2.5", "CC-BY-NC-3.0", "CC-BY-NC-4.0",
        "CC-BY-NC-SA", "CC-BY-NC-SA-1.0", "CC-BY-NC-SA-2.0", "CC-BY-NC-SA-2.5", "CC-BY-NC-SA-3.0", "CC-BY-NC-SA-4.0", # pylint: disable=line-too-long
        "CC-BY-NC-ND", "CC-BY-NC-ND-1.0", "CC-BY-NC-ND-2.0", "CC-BY-NC-ND-2.5", "CC-BY-NC-ND-3.0", "CC-BY-NC-ND-4.0", # pylint: disable=line-too-long
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
        "MPL-1.1",
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

    LICENSE_URLS = {
        "Apache"            : 'http://www.apache.org/licenses/LICENSE-1.0',
        "Apache-1.0"        : 'http://www.apache.org/licenses/LICENSE-1.0',
        "Apache-2.0"        : 'http://www.apache.org/licenses/LICENSE-2.0',
        "Artistic"          : 'http://www.gnu.org/licenses/license-list.en.html#ArtisticLicense',
        "Artistic-1.0"      : 'http://www.gnu.org/licenses/license-list.en.html#ArtisticLicense',
        "Artistic-2.0"      : 'http://www.perlfoundation.org/artistic_license_2_0',
        "BSD-2-clause"      : 'https://opensource.org/licenses/BSD-2-Clause',
        "BSD-3-clause"      : 'https://opensource.org/licenses/BSD-3-Clause',
        "ISC"               : 'https://opensource.org/licenses/ISC',
        "CC-BY"             : 'https://creativecommons.org/licenses/by/1.0/',
        "CC-BY-1.0"         : 'https://creativecommons.org/licenses/by/1.0/',
        "CC-BY-2.0"         : 'https://creativecommons.org/licenses/by/2.0/',
        "CC-BY-2.5"         : 'https://creativecommons.org/licenses/by/2.5/',
        "CC-BY-3.0"         : 'https://creativecommons.org/licenses/by/3.0/',
        "CC-BY-4.0"         : 'https://creativecommons.org/licenses/by/4.0/',
        "CC-BY-SA"          : 'https://creativecommons.org/licenses/by-sa/1.0/',
        "CC-BY-SA-1.0"      : 'https://creativecommons.org/licenses/by-sa/1.0/',
        "CC-BY-SA-2.0"      : 'https://creativecommons.org/licenses/by-sa/2.0/',
        "CC-BY-SA-2.5"      : 'https://creativecommons.org/licenses/by-sa/2.5/',
        "CC-BY-SA-3.0"      : 'https://creativecommons.org/licenses/by-sa/3.0/',
        "CC-BY-SA-4.0"      : 'https://creativecommons.org/licenses/by-sa/4.0/',
        "CC-BY-NC"          : 'https://creativecommons.org/licenses/by-nc/1.0/',
        "CC-BY-NC-1.0"      : 'https://creativecommons.org/licenses/by-nc/1.0/',
        "CC-BY-NC-2.0"      : 'https://creativecommons.org/licenses/by-nc/2.0/',
        "CC-BY-NC-2.5"      : 'https://creativecommons.org/licenses/by-nc/2.5/',
        "CC-BY-NC-3.0"      : 'https://creativecommons.org/licenses/by-nc/3.0/',
        "CC-BY-NC-4.0"      : 'https://creativecommons.org/licenses/by-nc/4.0/',
        "CC-BY-NC-SA"       : 'http://creativecommons.org/licenses/by-nc-sa/1.0/',
        "CC-BY-NC-SA-1.0"   : 'http://creativecommons.org/licenses/by-nc-sa/1.0',
        "CC-BY-NC-SA-2.0"   : 'http://creativecommons.org/licenses/by-nc-sa/2.0',
        "CC-BY-NC-SA-2.5"   : 'http://creativecommons.org/licenses/by-nc-sa/2.5',
        "CC-BY-NC-SA-3.0"   : 'http://creativecommons.org/licenses/by-nc-sa/3.0',
        "CC-BY-NC-SA-4.0"   : 'http://creativecommons.org/licenses/by-nc-sa/4.0',
        "CC-BY-NC-ND"       : 'https://creativecommons.org/licenses/by-nd-nc/1.0/',
        "CC-BY-NC-ND-1.0"   : 'https://creativecommons.org/licenses/by-nd-nc/1.0/',
        "CC-BY-NC-ND-2.0"   : 'https://creativecommons.org/licenses/by-nd-nc/2.0/',
        "CC-BY-NC-ND-2.5"   : 'https://creativecommons.org/licenses/by-nd-nc/2.5/',
        "CC-BY-NC-ND-3.0"   : 'https://creativecommons.org/licenses/by-nd-nc/3.0/',
        "CC-BY-NC-ND-4.0"   : 'https://creativecommons.org/licenses/by-nd-nc/4.0/',
        "CC-BY-ND"          : 'https://creativecommons.org/licenses/by-nd/1.0/',
        "CC-BY-ND-1.0"      : 'https://creativecommons.org/licenses/by-nd/1.0/',
        "CC-BY-ND-2.0"      : 'https://creativecommons.org/licenses/by-nd/2.0/',
        "CC-BY-ND-2.5"      : 'https://creativecommons.org/licenses/by-nd/2.5/',
        "CC-BY-ND-3.0"      : 'https://creativecommons.org/licenses/by-nd/3.0/',
        "CC-BY-ND-4.0"      : 'https://creativecommons.org/licenses/by-nd/4.0/',
        "CC0"               : 'https://creativecommons.org/publicdomain/zero/1.0/',
        "CDDL"              : 'https://opensource.org/licenses/CDDL-1.0',
        "CPL"               : 'https://opensource.org/licenses/cpl1.0.php',
        "EFL-1.0"           : 'https://opensource.org/licenses/ver1_eiffel',
        "EFL-2.0"           : 'https://opensource.org/licenses/EFL-2.0',
        "Expat"             : 'https://opensource.org/licenses/MIT',
        "MIT"               : 'https://opensource.org/licenses/MIT',
        "GPL-1.0"           : 'http://www.gnu.org/licenses/old-licenses/gpl-1.0.en.html',
        "GPL-2.0"           : 'http://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html',
        "GPL-3.0"           : 'http://www.gnu.org/licenses/gpl-3.0.en.html',
        "LGPL-2.0"          : 'https://www.gnu.org/licenses/old-licenses/lgpl-2.0.html',
        "LGPL-2.1"          : 'https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html',
        "LGPL-3.0"          : 'http://www.gnu.org/licenses/lgpl-3.0.en.html',
        "GFDL-1.1"          : 'http://www.gnu.org/licenses/old-licenses/fdl-1.1.en.html',
        "GFDL-1.2"          : 'http://www.gnu.org/licenses/old-licenses/fdl-1.2.html',
        "GFDL-1.3"          : 'http://www.gnu.org/licenses/fdl-1.3.en.html',
        "LPPL-1.0"          : 'https://latex-project.org/lppl/lppl-1-0.html',
        "LPPL-1.1"          : 'https://latex-project.org/lppl/lppl-1-1.html',
        "LPPL-1.2"          : 'https://latex-project.org/lppl/lppl-1-2.html',
        "LPPL-1.3c"         : 'https://latex-project.org/lppl/lppl-1-3c.html',
        "MPL-1.1"           : 'https://www.mozilla.org/en-US/MPL/1.1/',
        "Perl"              : 'http://dev.perl.org/licenses/',
        "Python-2.0"        : 'https://www.python.org/download/releases/2.0/license/',
        "QPL-1.0"           : 'https://opensource.org/licenses/QPL-1.0',
        "W3C"               : 'https://www.w3.org/Consortium/Legal/2015/copyright-software-and-document', # pylint: disable=line-too-long
        "Zlib"              : 'http://www.zlib.net/zlib_license.html',
        "Zope"              : 'http://old.zope.org/Resources/License.1',
        "Unlicense"         : 'https://unlicense.org/UNLICENSE',
    }

    EPOCH_VERSION_REGEXP = re.compile('^[0-9]+:')

    def __init__(self, collection, filename=None, contents=None):
        Ckan.__init__(self, filename, contents)
        self.collection = collection

    @property
    def can_mirror(self):
        return (
            self.kind == 'package'
            and getattr(self, 'download_content_type', '') in Ckan.MIME_TO_EXTENSION
            and self.redistributable
        )

    def mirrored(self, iarchive):
        item = iarchive.get_item(self.mirror_item())
        if not item:
            return False
        if not item.exists:
            return False
        sha1 = self.download_hash['sha1'].lower()
        return any(file['sha1'].lower() == sha1 for file in item.files if 'sha1' in file)

    def license_urls(self):
        return [self.LICENSE_URLS[lic]
                for lic in self.licenses() if lic in self.LICENSE_URLS]

    @property
    def redistributable(self):
        for lic in self.licenses():
            if lic in self.REDISTRIBUTABLE_LICENSES:
                return True
        return False

    def mirror_item(self, with_epoch=True):
        return '{}-{}'.format(
            self.identifier,
            self._format_version(with_epoch)
        )

    def mirror_filename(self, with_epoch=True):
        if not 'download_hash' in self._raw:
            return None
        return '{}-{}-{}.{}'.format(
            self.download_hash['sha1'][0:8],
            self.identifier,
            self._format_version(with_epoch),
            Ckan.MIME_TO_EXTENSION[self.download_content_type],
        )

    def mirror_source_filename(self, with_epoch=True):
        return '{}-{}.source.zip'.format(
            self.identifier,
            self._format_version(with_epoch)
        )

    def mirror_title(self, with_epoch=True):
        return '{} - {}'.format(
            self.name,
            self._format_version(with_epoch),
        )

    @property
    def item_metadata(self):
        lic_urls = self.license_urls()
        return {
            'title':       self.mirror_title(),
            'description': self.mirror_description,
            'creator':     self.authors(),
            'collection':  self.collection,
            'subject':     'ksp; kerbal space program; mod',
            'mediatype':   'software',
            **({'licenseurl': lic_urls} if lic_urls else {}),
        }

    def open_download(self):
        cached_file = self.cache_find_file
        if cached_file:
            # If the download is in the cache, use it
            logging.info('Found matching cache entry at %s', cached_file)
            return cached_file.open(mode='rb')
        # Download the file as needed
        with tempfile.NamedTemporaryFile() as tmp:
            logging.info('Downloading %s', self.download)
            urllib.request.urlretrieve(self.download, tmp.name)
            # Copy to cache so the temp file can be deleted
            shutil.copyfile(tmp.name, self.CACHE_PATH.joinpath(self.cache_filename))
            logging.info('Downloaded %s to %s', self.mirror_item(), self.cache_filename)
        return self.cache_find_file.open(mode='rb')

    @property
    def download_headers(self):
        return {
            'Content-Type':           self.download_content_type,
            'Content-Length':         str(self.download_size),
            'x-amz-auto-make-bucket': str(1),
        }

    @staticmethod
    def source_download_headers(file_path):
        return {
            'Content-Type':           "application/zip",
            'Content-Length':         str(os.path.getsize(file_path)),
            'x-amz-auto-make-bucket': str(1),
        }

    def _format_version(self, with_epoch):
        if with_epoch:
            return self.version.string.replace(':', '-')
        return self.EPOCH_VERSION_REGEXP.sub('', self.version.string)

    @property
    def mirror_description(self):
        descr = self.abstract + '<br>'
        resources = self._raw.get('resources')
        if resources:
            homepage = resources.get('homepage')
            if homepage:
                descr += f'<br>Homepage: <a href="{homepage}">{homepage}</a>'
            repository = resources.get('repository')
            if repository:
                descr += f'<br>Repository: <a href="{repository}">{repository}</a>'
        lic = self.licenses()
        if lic:
            descr += '<br>License(s): {}'.format(' '.join(lic))
        return descr
