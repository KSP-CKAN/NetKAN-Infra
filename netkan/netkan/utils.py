import logging
import subprocess
from git import Repo
from pathlib import Path


def init_repo(metadata, path):
    clone_path = Path(path)
    if not clone_path.exists():
        logging.info('Cloning {}'.format(metadata))
        repo = Repo.clone_from(metadata, clone_path)
    else:
        repo = Repo(clone_path)
    return repo


def init_ssh(key, path):
    if not key:
        logging.warning('Private Key required for SSH Git')
        return
    logging.info('Private Key found, writing to disk')
    key_path = Path(path)
    key_path.mkdir(exist_ok=True)
    key_file = Path(key_path, 'id_rsa')
    if not key_file.exists():
        key_file.write_text('{}\n'.format(key))
        key_file.chmod(0o400)
        scan = subprocess.run([
            'ssh-keyscan', '-t', 'rsa', 'github.com'
        ], stdout=subprocess.PIPE)
        Path(key_path, 'known_hosts').write_text(scan.stdout.decode('utf-8'))


def repo_file_add_or_changed(repo, filename):
    relative_file = Path(filename).relative_to(repo.working_dir).as_posix()
    if relative_file in repo.untracked_files:
        return True
    if relative_file in [
            x.a_path for x in repo.index.diff(None)]:
        return True
    return False
