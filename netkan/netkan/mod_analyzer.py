import re
import tempfile
from pathlib import Path
from zipfile import ZipFile, is_zipfile, ZipInfo
from typing import Dict, List, Any, Union, Pattern, Iterable

from .common import download_stream_to_file
from .cli.common import Game


class ModAspect:
    def __init__(self, tags: List[str], depends: List[str]) -> None:
        self.tags = tags
        self.depends = depends

    def apply_match(self, analyzer: 'ModAnalyzer') -> None:
        analyzer.tags += self.tags
        analyzer.depends += [{'name': dep} for dep in self.depends]

    def analyze(self, analyzer: 'ModAnalyzer') -> None:
        """
        Child classes should override this and call apply_match on a match
        """


class FilenameAspect(ModAspect):
    def __init__(self, name_regex: str, tags: List[str], depends: List[str]) -> None:
        super().__init__(tags, depends)
        self.name_pattern = re.compile(name_regex)

    def analyze(self, analyzer: 'ModAnalyzer') -> None:
        if analyzer.pattern_matches_any_filename(self.name_pattern):
            self.apply_match(analyzer)


class CfgAspect(ModAspect):

    def __init__(self, cfg_regex: str, tags: List[str], depends: List[str]) -> None:
        super().__init__(tags, depends)
        self.cfg_pattern = re.compile(cfg_regex, re.MULTILINE)

    def analyze(self, analyzer: 'ModAnalyzer') -> None:
        if analyzer.pattern_matches_any_cfg(self.cfg_pattern):
            self.apply_match(analyzer)


class ModAnalyzer:

    ASPECTS: List[ModAspect] = [
        CfgAspect(r'^\s*[@+$\-!%]|^\s*[a-zA-Z0-9_]+:',
                                            [],               ['ModuleManager']),
        CfgAspect(r'^\s*PART\b',            ['parts'],        []),
        CfgAspect(r'^\s*INTERNAL\b',        ['crewed'],       []),
        CfgAspect(r'^\s*@TechTree\b',       ['tech-tree'],    []),
        CfgAspect(r'^\s*@Kopernicus\b',     ['planet-pack'],  ['Kopernicus']),
        CfgAspect(r'^\s*STATIC\b',          ['buildings'],    ['KerbalKonstructs']),
        CfgAspect(r'^\s*TUFX_PROFILE\b',    ['graphics'],     ['TUFX']),
        CfgAspect(r'^\s*CONTRACT_TYPE\b',   ['career'],       ['ContractConfigurator']),
        CfgAspect(r'^\s*@CUSTOMBARNKIT\b',  [],               ['CustomBarnKit']),
        CfgAspect(r'^\s*name\s*=\s*ModuleB9PartSwitch\b',
                                            [],               ['B9PartSwitch']),
        CfgAspect(r'^\s*name\s*=\s*ModuleWaterfallFX\b',
                                            ['graphics'],     ['Waterfall']),
        CfgAspect(r'^\s*VertexMitchellNetravaliHeightMap\b',
                                            [],               ['VertexMitchellNetravaliHeightMap']),

        FilenameAspect(r'\.ks$',            ['config',
                                             'control'],      ['kOS']),
        FilenameAspect(r'swinfo\.json$',    [],               ['SpaceWarp']),
        FilenameAspect(r'\.dll$',           ['plugin'],       []),
        FilenameAspect(r'\.cfg$',           ['config'],       []),
    ]
    FILTERS = [
        '__MACOSX', '.DS_Store',
        'Thumbs.db',
        '.git', '.gitignore',
    ]
    FILTER_REGEXPS = [
        r'\.mdb$', r'\.pdb$',
        r'~$',     r'\.craft$',
    ]
    # None = subassembly
    CRAFT_TYPE_REGEXP = re.compile(r'^\s*type = (?P<type>VAB|SPH|None)',
                                   re.MULTILINE)

    def __init__(self, ident: str, download_url: str, game: Game) -> None:
        self.ident = ident
        self.download_file = tempfile.NamedTemporaryFile()
        download_stream_to_file(download_url, self.download_file)
        self.download_file.flush()
        self.zip = (ZipFile(self.download_file, 'r')
                    if is_zipfile(self.download_file)
                    else None)
        # Dir entries are optional, so try to ignore them
        self.files = ([] if not self.zip else
                      [zi for zi in self.zip.infolist()
                       if not zi.is_dir()])

        self.mod_root_path = game.mod_root

        self.tags: List[str] = []
        self.depends: List[Dict[str, str]] = []
        for aspect in self.ASPECTS:
            aspect.analyze(self)
        if 'parts' in self.tags:
            self.tags.remove('config')

        self.default_install_stanza = {'find':       ident,
                                       'install_to': self.mod_root_path}

    def read_zipped_file(self, zipinfo: ZipInfo) -> str:
        return ('' if not self.zip else
                self.zip.read(zipinfo.filename).decode('utf-8-sig',
                                                       errors='ignore'))

    def has_version_file(self) -> bool:
        return any(zi.filename.lower().endswith('.version')
                   for zi in self.files)

    def has_spacewarp_info(self) -> bool:
        return any(zi.filename.lower().endswith('swinfo.json')
                   for zi in self.files)

    def has_dll(self) -> bool:
        return any(zi.filename.lower().endswith('.dll')
                   for zi in self.files)

    def has_cfg(self) -> bool:
        return any(zi.filename.lower().endswith('.cfg')
                   for zi in self.files)

    def pattern_matches_any_filename(self, pattern: Pattern[str]) -> bool:
        return (False if not self.zip
                else any(pattern.search(zi.filename)
                         for zi in self.files))

    def pattern_matches_any_cfg(self, pattern: Pattern[str]) -> bool:
        return (False if not self.zip
                else any(zi.filename.lower().endswith('.cfg')
                         and pattern.search(self.read_zipped_file(zi))
                         for zi in self.files))

    def get_crafts(self) -> List[ZipInfo]:
        return [zi for zi in self.files
                if zi.filename.lower().endswith('.craft')]

    def get_ship_type(self, zipinfo: ZipInfo) -> str:
        match = self.CRAFT_TYPE_REGEXP.search(self.read_zipped_file(zipinfo))
        return match.group('type') if match else ''

    def has_ident_folder(self) -> bool:
        return any(self.ident in Path(zi.filename).parts[:-1]
                   for zi in self.files)

    @staticmethod
    def sublists(main_list: List[str], sublist_len: int) -> Iterable[List[str]]:
        return (main_list[start : start + sublist_len]
                for start in range(len(main_list) - sublist_len + 1))

    @staticmethod
    def iter_index(container: List[str], contained: List[str]) -> int:
        for start, sublist in enumerate(ModAnalyzer.sublists(container, len(contained))):
            if sublist == contained:
                return start
        return -1

    def find_folder(self) -> str:
        gamedata_folded = self.mod_root_path.casefold().split('/')
        gamedata_len = len(gamedata_folded)
        # First look for a unique entry directly under GameData
        dir_parts = {Path(zi.filename).parts[:-1] for zi in self.files}
        dir_parts_folded = [(dirs, [d.casefold() for d in dirs])
                            for dirs in dir_parts]
        dirs_with_gamedata = {(dirs, ModAnalyzer.iter_index(dirs_folded, gamedata_folded))
                              for dirs, dirs_folded in dir_parts_folded
                              if ModAnalyzer.iter_index(dirs_folded, gamedata_folded) > -1}
        parts_after_gd = {dirs[i + gamedata_len]: f'{dirs[i]}/{dirs[i + gamedata_len]}'
                          for dirs, i in dirs_with_gamedata
                          if i < len(dirs) - 1}
        if len(parts_after_gd) > 1:
            # Multiple folders under GameData, manual review required
            # unless one of them is the identifier
            return (parts_after_gd[self.ident]
                    if self.ident in parts_after_gd
                    else '')
        if len(parts_after_gd) == 1:
            # Found GameData with only one subdir, return it
            return next(iter(parts_after_gd))
        # No GameData, find the identifier anywhere else
        if self.has_ident_folder():
            return self.ident
        # No GameData and no identifier folder, look for unique folder in root
        first_parts = {dirs[0] for dirs in dir_parts if len(dirs) > 0}
        if len(first_parts) == 1:
            # No GameData but only one root folder, return it
            return next(iter(first_parts))
        # No GameData, multiple folders in root, no identifier folder;
        # manual review required
        return ''

    def get_filters(self) -> List[str]:
        return [filt for filt in self.FILTERS
                # Normal filter are case insensitive
                if any(filt.casefold() in Path(zi.filename.casefold()).parts
                       for zi in self.files)]

    def get_filter_regexps(self) -> List[str]:
        return [filt for filt in self.FILTER_REGEXPS
                # Regex filters are case sensitive
                if any(re.search(filt, zi.filename)
                       for zi in self.files)]

    def get_ships_install_stanzas(self) -> List[Dict[str, Any]]:
        paths_with_type = [(Path(craft.filename), self.get_ship_type(craft))
                           for craft in self.get_crafts()]
        return [{'file': path.as_posix(),
                 'install_to': f'Ships/{type}'}
                for path, type in paths_with_type
                if type != 'None']

    def get_install_stanzas(self) -> Dict[str, List[Dict[str, Any]]]:
        stanzas: List[Dict[str, Any]] = [{'find': self.find_folder(),
                                          'install_to': self.mod_root_path},
                                         *self.get_ships_install_stanzas()]
        filters = self.get_filters()
        filter_regexps = self.get_filter_regexps()
        if filters:
            stanzas[0]['filter'] = ModAnalyzer.flatten(filters)
        if filter_regexps:
            stanzas[0]['filter_regexp'] = ModAnalyzer.flatten(filter_regexps)

        if len(stanzas) == 1 and self.default_install_stanza in stanzas:
            stanzas.remove(self.default_install_stanza)
        return {'install': stanzas} if stanzas else {}

    @staticmethod
    def flatten(a_list: List[str]) -> Union[List[str], str]:
        return a_list[0] if len(a_list) == 1 else a_list

    def get_netkan_properties(self) -> Dict[str, Any]:
        props: Dict[str, Any] = {}
        if self.has_version_file():
            props['$vref'] = '#/ckan/ksp-avc'
        if self.has_spacewarp_info():
            props['$vref'] = '#/ckan/space-warp'
        if self.tags:
            props['tags'] = self.tags
        if self.depends:
            props['depends'] = self.depends
        props.update(self.get_install_stanzas())
        return props
