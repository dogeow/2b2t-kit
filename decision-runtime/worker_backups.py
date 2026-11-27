"""List or prune old material-worker code backups left by material_worker_release installs.

Each install moves the previous worker (~8 MB of source) to config/twob2tkit/backups/material-worker-<time>.
Nothing ever removed them. This keeps the newest N and, only with --apply, deletes the rest. It touches
nothing but directories whose name is exactly that release-tool pattern; other backups are left alone.

Usage: python worker_backups.py [--game-dir DIR] [--keep 10] [--apply]
"""
import argparse
import json
from pathlib import Path
import re
import shutil

DEFAULT_GAME = Path('/Applications/.minecraft/versions/26.2')
NAME = re.compile(r'material-worker-\d{8}-\d{6}-\d{6}')


def _size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())


def prune(game, keep=10, apply=False):
    if keep < 1:
        raise ValueError('Keep at least one worker backup')
    root = Path(game) / 'config/twob2tkit/backups'
    if root.is_symlink():
        raise ValueError('Refusing a symlinked backups folder')
    found = sorted((p for p in root.iterdir() if NAME.fullmatch(p.name) and p.is_dir() and not p.is_symlink()),
                   key=lambda p: p.name, reverse=True) if root.is_dir() else []
    victims = found[keep:]
    report = {'mode': 'delete' if apply else 'dry_run', 'kept': [p.name for p in found[:keep]],
              'remove': len(victims), 'remove_bytes': sum(_size(p) for p in victims),
              'oldest_removed': victims[-1].name if victims else None, 'newest_removed': victims[0].name if victims else None}
    if apply:
        for path in victims:
            shutil.rmtree(path)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--game-dir', type=Path, default=DEFAULT_GAME)
    parser.add_argument('--keep', type=int, default=10)
    parser.add_argument('--apply', action='store_true', help='actually delete; default only lists')
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prune(args.game_dir, args.keep, args.apply), ensure_ascii=False)); return 0
    except (OSError, ValueError) as error:
        print(json.dumps({'mode': 'blocked', 'error': str(error)}, ensure_ascii=False)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
