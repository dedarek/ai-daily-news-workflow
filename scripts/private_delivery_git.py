"""Read and checkpoint delivery records in a provisioned, private Git checkout."""
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def storage():
    raw = os.environ.get('AI_DAILY_PRIVATE_STATE_DIR')
    if not raw:
        raise RuntimeError('Private delivery storage is required')
    path = Path(raw).resolve()
    if path != ROOT / 'private-delivery' or not (path / '.git').is_dir():
        raise RuntimeError('Invalid private delivery checkout')
    return path


def git(*args):
    child = subprocess.run(['git', '-C', str(storage()), *args],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return child.returncode


def checkpoint(path):
    rel = path.resolve().relative_to(storage()).as_posix()
    if not rel.startswith('state/') or not rel.endswith('.json'):
        raise RuntimeError('Unexpected delivery state path')
    if git('add', '--', rel) != 0:
        raise RuntimeError('Private delivery git add failed')
    diff = git('diff', '--cached', '--quiet', '--', rel)
    if diff not in (0, 1):
        raise RuntimeError('Private delivery git diff failed')
    if diff and git('commit', '-q', '-m', 'Checkpoint newsletter delivery', '--', rel) != 0:
        raise RuntimeError('Private delivery git commit failed')
    if git('push', '-q', 'origin', 'HEAD:main') != 0:
        raise RuntimeError('Private delivery state push failed; stopping SMTP')
