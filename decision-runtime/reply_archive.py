"""Lossless, explicit disk maintenance for old read-only scan replies.

Never archives mutation receipts, malformed records, current requests, or replies
referenced by local journals. Verified gzip stays next to each original filename.
No game commands, reconnect, task replay, or JSON success-state rewriting.
"""
import argparse
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

REFS = re.compile(r'"(?:id|request_id|last_request)"\s*:\s*"([A-Za-z0-9_-]+)"|reply-([A-Za-z0-9_-]+)\.json')
NAME = re.compile(r'reply-([A-Za-z0-9_-]+)\.json')
MAX_REPLY = 16 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def references(root):
    ids = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith('.') and not Path(directory, d).is_symlink()]
        for name in files:
            if name.startswith('reply-') or not name.endswith('.json'):
                continue
            path = Path(directory, name)
            if path.is_symlink():
                raise ValueError('Refusing symlinked journal')
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('Journal exceeds bounded reference scan; archive cancelled')
            content = path.read_text(errors='strict')
            # Conservative: pin every referenced request, including completed ones.
            for match in REFS.finditer(content):
                ids.add(match.group(1) or match.group(2))
    return ids


def eligible(path, pinned, cutoff):
    match = NAME.fullmatch(path.name)
    if not match or path.is_symlink() or match.group(1) in pinned:
        return None
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_mtime >= cutoff or metadata.st_size > MAX_REPLY:
        return None
    raw = path.read_bytes()
    try:
        record = json.loads(raw)
    except (ValueError, UnicodeError):
        return None
    if not isinstance(record, dict) or record.get('id') != match.group(1):
        return None
    # Historical synchronous scan responses have no op/phase but an exact
    # top-level blocks array. New replies explicitly identify scan completion.
    if not isinstance(record.get('blocks'), list):
        return None
    if any(k in record for k in ('phase', 'op', 'error', 'result', 'pending', 'intent', 'request')):
        return None
    if record.get('scan_complete') is False:
        return None
    for row in record['blocks']:
        if not isinstance(row, dict) or not isinstance(row.get('state'), str) or not isinstance(row.get('pos'), list) or len(row['pos']) != 3:
            return None
    return raw, metadata


def pack(path, raw, metadata):
    destination = path.with_name(path.name + '.gz')
    if destination.exists() or destination.is_symlink():
        raise ValueError('Archive already exists; refusing overwrite')
    fd, temporary = tempfile.mkstemp(prefix='.reply-archive-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            with gzip.GzipFile(filename=path.name, fileobj=stream, mode='wb', mtime=int(metadata.st_mtime), compresslevel=6) as compressed:
                compressed.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        with gzip.open(temporary, 'rb') as stream:
            restored = stream.read(MAX_REPLY + 1)
        if digest(restored) != digest(raw):
            raise ValueError('Archive verification failed; original retained')
        now = path.stat()
        if (now.st_ino, now.st_size, now.st_mtime_ns) != (metadata.st_ino, metadata.st_size, metadata.st_mtime_ns) or path.read_bytes() != raw:
            raise ValueError('Original changed; archive cancelled')
        # Hard-link commit refuses overwrite even if another file appeared.
        os.link(temporary, destination)
        os.chmod(destination, 0o600)
        os.utime(destination, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        path.unlink()
        return destination.stat().st_size
    finally:
        Path(temporary).unlink(missing_ok=True)


def archive(root, *, days=7, apply=False, max_files=2000, now=None):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Automation root must be a real directory')
    if days < 1 or max_files < 1:
        raise ValueError('Keep at least one day and use a positive batch limit')
    result = {'mode': 'archive' if apply else 'dry_run', 'files': 0, 'original_bytes': 0, 'compressed_bytes': 0}
    cutoff = (time.time() if now is None else now) - days * 86400
    with (root / '.reply-archive.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pinned = references(root)
        result['pinned_requests'] = len(pinned)
        for path in sorted(root.glob('reply-*.json')):
            candidate = eligible(path, pinned, cutoff)
            if candidate is None:
                continue
            raw, metadata = candidate
            size = pack(path, raw, metadata) if apply else 0
            result['files'] += 1
            result['original_bytes'] += len(raw)
            result['compressed_bytes'] += size
            if result['files'] >= max_files:
                break
    result['recovered_bytes'] = result['original_bytes'] - result['compressed_bytes'] if apply else 0
    return result


def restore(root, name):
    root = Path(root)
    if not NAME.fullmatch(name) or root.is_symlink():
        raise ValueError('Use a plain reply filename')
    destination, packed = root / name, root / (name + '.gz')
    if packed.is_symlink() or destination.exists() or destination.is_symlink():
        raise ValueError('Original exists or archive is symlinked; refusing overwrite')
    with gzip.open(packed, 'rb') as stream:
        raw = stream.read(MAX_REPLY + 1)
    if len(raw) > MAX_REPLY:
        raise ValueError('Archive exceeds reply size bound')
    metadata = packed.stat()
    fd, temporary = tempfile.mkstemp(prefix='.reply-restore-', dir=root)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        os.link(temporary, destination)
        os.utime(destination, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {'restored': name, 'bytes': len(raw), 'sha256': digest(raw)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--max-files', type=int, default=2000)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--restore')
    args = parser.parse_args(argv)
    try:
        result = restore(args.root, args.restore) if args.restore else archive(args.root, days=args.days, apply=args.apply, max_files=args.max_files)
        print(json.dumps(result, ensure_ascii=False)); return 0
    except (OSError, ValueError, UnicodeError) as error:
        print(json.dumps({'mode': 'blocked', 'error': str(error)}, ensure_ascii=False)); return 2


if __name__ == '__main__':
    raise SystemExit(main())
