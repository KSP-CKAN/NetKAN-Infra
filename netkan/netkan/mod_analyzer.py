import re
import tempfile
from pathlib import Path
from zipfile import ZipFile, is_zipfile
from typing import Dict, Any
import requests


class ModAnalyzer:

    USER_AGENT = 'Mozilla/5.0 (compatible; Netkanbot/1.0; CKAN; +https://github.com/KSP-CKAN/NetKAN-Infra'
    MM_PATTERN = re.compile(r'^\s*[@+$\-!%]|^\s*[a-zA-Z0-9_]+:',
                            re.MULTILINE)
    PARTS_PATTERN = re.compile(r'^\s*PART\b',
                               re.MULTILINE)

    def __init__(self, ident: str, download_url: str) -> None:
        self.ident = ident
        self.download_file = tempfile.NamedTemporaryFile()
        self.download_file.write(requests.get(
            download_url,
            headers={ 'User-Agent': self.USER_AGENT }
        ).content)
        self.download_file.flush()
        self.zip = (ZipFile(self.download_file, 'r')
                    if is_zipfile(self.download_file)
                    else None)
        # Dir entries are optional, so try to ignore them
        self.files = ([] if not self.zip else
                      [zi for zi in self.zip.infolist()
                       if not zi.is_dir()])

    def has_version_file(self) -> bool:
        return any(zi.filename.lower().endswith('.version')
                   for zi in self.files)

    def has_dll(self) -> bool:
        return any(zi.filename.lower().endswith('.dll')
                   for zi in self.files)

    def has_cfg(self) -> bool:
        return any(zi.filename.lower().endswith('.cfg')
                   for zi in self.files)

    def str_has_mm_syntax(self, cfg_str: str) -> bool:
        return self.MM_PATTERN.search(cfg_str) is not None

    def has_mm_syntax(self) -> bool:
        return (False if not self.zip
                else any(zi.filename.lower().endswith('.cfg')
                         and self.str_has_mm_syntax(
                             self.zip.read(zi.filename).decode("utf-8"))
                         for zi in self.files))

    def str_has_parts(self, cfg_str: str) -> bool:
        return self.PARTS_PATTERN.search(cfg_str) is not None

    def has_parts(self) -> bool:
        return (False if not self.zip
                else any(zi.filename.lower().endswith('.cfg')
                         and self.str_has_parts(
                             self.zip.read(zi.filename).decode("utf-8"))
                         for zi in self.files))

    def has_ident_folder(self) -> bool:
        return any(self.ident in Path(zi.filename).parts[:-1]
                   for zi in self.files)

    def find_folder(self) -> str:
        # First look for a unique entry directly under GameData
        dir_parts = {Path(zi.filename).parts[:-1] for zi in self.files}
        dirs_with_gamedata = {(dirs, dirs.index('GameData'))
                              for dirs in dir_parts
                              if 'GameData' in dirs}
        parts_after_gd = {dirs[i + 1]
                          for dirs, i in dirs_with_gamedata
                          if i < len(dirs) - 1}
        if len(parts_after_gd) > 1:
            # Multiple folders under GameData, manual review required
            return ''
        if len(parts_after_gd) == 1:
            # Found GameData with only one subdir, return it
            return next(iter(parts_after_gd))
        # If no GameData, look for unique folder in root
        first_parts = {dirs[0] for dirs in dir_parts}
        if len(first_parts) == 1:
            # No GameData but only one root folder, return it
            return next(iter(first_parts))
        # No GameData, multiple folders in root, manual review required
        return ''

    def get_netkan_properties(self) -> Dict[str, Any]:
        props: Dict[str, Any] = { }
        if self.has_version_file():
            props['$vref'] = '#/ckan/ksp-avc'
        props['tags'] = []
        if self.has_dll():
            props['tags'].append('plugin')
        if self.has_parts():
            props['tags'].append('parts')
        elif self.has_cfg():
            # Mark .cfg files with no parts as config
            props['tags'].append('config')
        if self.has_mm_syntax():
            props['depends'] = [ {
                'name': 'ModuleManager'
            } ]
        if not self.has_ident_folder():
            props['install'] = [ {
                'find': self.find_folder(),
                'install_to': 'GameData'
            } ]
        return props
