import logging
import subprocess
from pathlib import Path
from typing import Union
from importlib.resources import files

from git import Repo


def init_repo(metadata: str, path: str, deep_clone: bool) -> Repo:
    clone_path = Path(path)
    if not clone_path.exists():
        logging.info('Cloning %s', metadata)
        repo = (Repo.clone_from(metadata, clone_path)
                if deep_clone else
                Repo.clone_from(metadata, clone_path, depth=1))
    else:
        repo = Repo(clone_path)
    return repo


def init_ssh(key: str, key_path: Path) -> None:
    if not key:
        logging.warning('Private key required for SSH Git')
        return
    logging.info('Private Key found, writing to disk')
    key_path.mkdir(exist_ok=True)
    key_file = Path(key_path, 'id_rsa')
    if not key_file.exists():
        key_file.write_text(f'{key}\n', encoding='UTF-8')
        key_file.chmod(0o400)
        scan = subprocess.run([
            'ssh-keyscan', '-t', 'rsa', 'github.com'
        ], stdout=subprocess.PIPE, check=False)
        Path(key_path, 'known_hosts').write_text(scan.stdout.decode('utf-8'), encoding='UTF-8')


def repo_file_add_or_changed(repo: Repo, filename: Union[str, Path]) -> bool:
    if repo.working_dir:
        relative_file = Path(filename).relative_to(repo.working_dir).as_posix()
        if relative_file in repo.untracked_files:
            return True
        if relative_file in [
                x.a_path for x in repo.index.diff(None)]:
            return True
    return False


def legacy_read_text(pkg: str, resource: str) -> str:
    return files(pkg).joinpath(resource).read_text()
