"""Build/verify a reproducible source-only material worker; install only on explicit CLI request.

No game launch, model call, credential copy or network access is performed.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ENTRYPOINTS = ('material_jobs_cli', 'material_jobs_backend')
EXCLUDED_DIRS = {'__pycache__', 'tests', 'cases', 'lessons', 'state', 'config', 'cache', 'venv', '.venv', 'vendor'}
EXCLUDED_FILES = {'set_key.py', 'benchmark.py', 'playground.py', 'check_offline.py',
                  'kit_release.py', 'material_worker_release.py', 'install_observer.py'}
MAX_BUNDLE = 16 * 1024 * 1024
SECRET = re.compile(rb'(?:apikey_[a-fA-F0-9]{24,}_[a-fA-F0-9]{24,}|sk-(?:proj-)?[A-Za-z0-9_-]{40,})')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def allowed_python(relative):
    return (relative.suffix == '.py' and relative.name not in EXCLUDED_FILES
            and not relative.name.startswith('test_') and not relative.name.endswith('_test.py')
            and all(part not in EXCLUDED_DIRS and not part.startswith('.') for part in relative.parts))


def collect(source):
    source = Path(source).resolve()
    files = {}
    roots = [(source, '')]
    companion = source.parent / 'companion-skills' / 'kit_skills'
    if companion.is_dir():
        roots.append((companion, 'kit_skills/'))
    for root, prefix in roots:
        for path in sorted(root.rglob('*.py')):
            relative = path.relative_to(root)
            if not allowed_python(relative):
                continue
            if path.is_symlink() or root.resolve() not in path.resolve().parents:
                raise ValueError(f'Refusing source symlink: {prefix}{relative.as_posix()}')
            data = path.read_bytes()
            if SECRET.search(data):
                raise ValueError(f'Credential-like literal in source: {prefix}{relative.as_posix()}')
            ast.parse(data, filename=str(relative))
            files[prefix + relative.as_posix()] = data
    requirements = source / 'requirements.txt'
    if requirements.is_file():
        data = requirements.read_bytes()
        for line in data.decode().splitlines():
            if line.strip() and not re.fullmatch(r'[A-Za-z0-9_.-]+==[A-Za-z0-9_.+-]+', line.strip()):
                raise ValueError('Worker requirements must contain pinned package names only')
        files['requirements.txt'] = data
    for entry in ENTRYPOINTS:
        if entry + '.py' not in files:
            raise ValueError(f'Required material worker entry point is missing: {entry}')
    if sum(map(len, files.values())) > MAX_BUNDLE:
        raise ValueError('Material worker source bundle exceeds size limit')
    return files


def build(source, output):
    files = collect(source)
    manifest = {'schema': 1, 'entrypoints': list(ENTRYPOINTS),
                'files': {name: sha(data) for name, data in sorted(files.items())}}
    files['worker-manifest.json'] = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.material-worker-', suffix='.zip', dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        verify(temporary)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {'bundle': str(output), 'sha256': sha(output.read_bytes()), 'files': len(manifest['files'])}


def verify(bundle):
    with zipfile.ZipFile(bundle) as archive:
        infos = archive.infolist()
        if len(infos) > 1024 or sum(info.file_size for info in infos) > MAX_BUNDLE:
            raise ValueError('Worker archive size exceeds limit')
        names = [info.filename for info in infos]
        if len(set(names)) != len(names):
            raise ValueError('Duplicate worker archive entry')
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or path.as_posix() != name:
                raise ValueError('Invalid worker archive path')
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Worker archive symlinks are forbidden')
            if name not in ('worker-manifest.json', 'requirements.txt') and not allowed_python(path):
                raise ValueError('Worker archive contains a non-source file')
        manifest = json.loads(archive.read('worker-manifest.json'))
        if manifest.get('schema') != 1 or manifest.get('entrypoints') != list(ENTRYPOINTS):
            raise ValueError('Invalid worker manifest')
        expected = manifest.get('files')
        if not isinstance(expected, dict) or set(expected) != set(names) - {'worker-manifest.json'}:
            raise ValueError('Worker manifest does not cover archive contents')
        files = {}
        for name, digest in expected.items():
            data = archive.read(name)
            if sha(data) != digest or SECRET.search(data):
                raise ValueError(f'Worker source verification failed: {name}')
            files[name] = data
        for entry in ENTRYPOINTS:
            if entry + '.py' not in files:
                raise ValueError('Worker entry point missing')
        files['worker-manifest.json'] = archive.read('worker-manifest.json')
        return files


def check_imports(bundle, python=sys.executable):
    """Load only module definitions in an isolated temp tree. Network/game actions are denied."""
    files = verify(bundle)
    with tempfile.TemporaryDirectory(prefix='material-worker-imports-') as temporary:
        root = Path(temporary)
        for name, data in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if path.read_bytes() != data:
                raise RuntimeError('Staged worker content mismatch')
        code = '''import importlib, pathlib, socket, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
def deny(*args, **kwargs): raise RuntimeError("Worker import attempted an external operation")
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
def audit(event, args):
    if event in ("subprocess.Popen", "os.system", "os.fork", "socket.connect"):
        deny()
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = pathlib.Path(args[0]).resolve()
        if path.suffix in (".key", ".json", ".sqlite", ".db") and root not in path.parents:
            deny()
sys.addaudithook(audit)
for name in ("material_jobs_cli", "material_jobs_backend"):
    importlib.import_module(name)
print("material worker imports passed")
'''
        result = subprocess.run([str(python), '-B', '-I', '-c', code, str(root)], cwd=root,
                                text=True, capture_output=True, timeout=30)
        if result.returncode:
            # Report a bounded import diagnostic; the sandboxed import cannot read key/config files.
            raise RuntimeError('Worker import check failed:\n' + result.stderr[-3000:])
    return {'imports': list(ENTRYPOINTS), 'passed': True}


def worker_running():
    result = subprocess.run(['pgrep', '-f', 'material_jobs_cli.py'], capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise RuntimeError('Cannot determine worker state; deployment refused')
    return result.returncode == 0


def runtime_python_bytes(python):
    value=os.fspath(python)
    if (not value or len(value.encode())>4095 or any(ord(char)<32 or ord(char)==127 for char in value)
            or not Path(value).is_absolute()):
        raise ValueError('Runtime Python must be one absolute local path')
    if not Path(value).is_file() or not os.access(value,os.X_OK):
        raise ValueError('Runtime Python is not an executable file')
    # Keep the venv executable spelling. Path.resolve() would discard the venv.
    return (value+'\n').encode()


def install(bundle, game, *, python=sys.executable, running=worker_running):
    """Explicit source deployment, backed up and rolled back on error. Never launches anything."""
    if running():
        raise RuntimeError('A material worker is running; stop it before deployment')
    files = verify(bundle)
    files['runtime-python.txt'] = runtime_python_bytes(python)
    destination = Path(game) / 'config' / 'twob2tkit' / 'material-worker'
    if destination.is_symlink():
        raise ValueError('Refusing a symlinked worker destination')
    destination.parent.mkdir(parents=True, exist_ok=True)
    manifest = files['worker-manifest.json']
    if (destination / 'worker-manifest.json').is_file() and (destination / 'worker-manifest.json').read_bytes() == manifest:
        if all((destination / name).is_file() and (destination / name).read_bytes() == data for name, data in files.items()):
            return {'installed': str(destination), 'runtime_python':os.fspath(python), 'unchanged': True}
    stage = Path(tempfile.mkdtemp(prefix='.material-worker-stage-', dir=destination.parent))
    backup = destination.parent / 'backups' / ('material-worker-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    moved_old = False
    try:
        for name, data in files.items():
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if path.read_bytes() != data:
                raise RuntimeError('Staged worker content mismatch')
        if running():
            raise RuntimeError('A material worker started during staging; deployment refused')
        if destination.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            destination.rename(backup)
            moved_old = True
        try:
            stage.rename(destination)
        except Exception:
            if moved_old:
                backup.rename(destination)
            raise
        return {'installed': str(destination), 'backup': str(backup) if moved_old else None,
                'files': len(files) - 2, 'runtime_python':os.fspath(python), 'manifest_sha256': sha(manifest)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--out', type=Path, required=True, help='Reproducible source ZIP path')
    parser.add_argument('--check-imports', action='store_true')
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--install-game', type=Path, help='Explicitly install into this game profile; omit to only build')
    args = parser.parse_args(argv)
    try:
        result = build(args.source, args.out)
        if args.check_imports or args.install_game:
            result['verification'] = check_imports(args.out, args.python)
        if args.install_game:
            result['deployment'] = install(args.out, args.install_game, python=args.python)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, SyntaxError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        parser.exit(2, f'material-worker-release: {error}\n')


if __name__ == '__main__':
    main()
