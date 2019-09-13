import logging
import subprocess
import sys
from git import Repo
from pathlib import Path


def init_repo(metadata, path):
    clone_path = Path(path)
    if not clone_path.exists():
        logging.info('Cloning {}'.format(metadata))
        clone_path.mkdir(parents=True)
        repo = Repo.init(clone_path)
        repo.create_remote('origin', metadata)
        repo.remotes.origin.pull('master:master')
    else:
        repo = Repo(clone_path)
    return repo


def init_ssh(key, path):
    if not key:
        logging.error('Private Key required for SSH Git')
        sys.exit(1)
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
