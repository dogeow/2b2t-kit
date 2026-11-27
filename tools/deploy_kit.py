"""Install the built Kit main jar and runtime engine into the game, the way AGENTS.md describes.

- Versions come from gradle.properties; the built engine's manifest must match runtime_engine_version.
- Every old twob2tkit-*.jar in mods/ moves to mod-backups/ so exactly one Kit jar stays; the old engine
  is copied to config/twob2tkit/runtime/backups/. New files land via a temporary name and a rename.
- SHA-256 of each installed file is checked against the build. Nothing else in the game folder is touched.

Usage: python tools/deploy_kit.py [--engine-only] [--dry-run] [--game-dir DIR]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_GAME = Path('/Applications/.minecraft/versions/26.2')


class DeployError(RuntimeError):
    pass


def properties(project):
    values = {}
    for line in Path(project, 'gradle.properties').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1); values[key.strip()] = value.strip()
    return values


def engine_version(jar):
    with zipfile.ZipFile(jar) as archive:
        for line in archive.read('META-INF/MANIFEST.MF').decode('utf-8', 'replace').splitlines():
            if line.startswith('twob2tkit-Engine-Version:'):
                return line.split(':', 1)[1].strip()
    return None


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def _install(source, target):
    temporary = target.with_name('.' + target.name + '.tmp')
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def plan(project, game, engine_only=False):
    props = properties(project)
    version, engine = props.get('version'), props.get('runtime_engine_version')
    main_jar = Path(project, 'build/libs', f'twob2tkit-{version}.jar')
    engine_jar = Path(project, 'build/runtime-engine/twob2tkit-engine.jar')
    if not engine_jar.is_file():
        raise DeployError('没有构建好的引擎，先运行 gradlew jar verifyRuntimeEngineJar')
    built_engine = engine_version(engine_jar)
    if built_engine != engine:
        raise DeployError(f'构建出的引擎是 {built_engine}，gradle.properties 写的是 {engine}；先重新构建')
    if not engine_only and not main_jar.is_file():
        raise DeployError(f'没有 {main_jar.name}，先运行 gradlew jar')
    mods = Path(game, 'mods')
    if not mods.is_dir():
        raise DeployError(f'游戏目录不对：{game} 下没有 mods/')
    old = sorted(mods.glob('twob2tkit-*.jar'))  # a same-version reinstall is backed up too
    return {'version': version, 'engine_version': engine, 'main_jar': main_jar, 'engine_jar': engine_jar,
            'old_main_jars': [] if engine_only else old, 'engine_only': engine_only}


def deploy(project, game, engine_only=False, dry_run=False, stamp=None):
    p = plan(project, game, engine_only)
    stamp = stamp or time.strftime('%Y%m%d-%H%M%S')
    game = Path(game)
    runtime = game / 'config/twob2tkit/runtime'
    installed_engine = runtime / 'twob2tkit-engine.jar'
    report = {'version': p['version'], 'engine_version': p['engine_version'], 'dry_run': dry_run, 'backups': [], 'installed': {}}
    if dry_run:
        report['would_move_to_backups'] = [j.name for j in p['old_main_jars']]
        return report
    if not engine_only:
        backups = game / 'mod-backups'; backups.mkdir(exist_ok=True)
        for jar in p['old_main_jars']:
            target = backups / f'{jar.stem}-{stamp}.jar'
            shutil.move(str(jar), target); report['backups'].append(str(target))
        target = game / 'mods' / p['main_jar'].name
        _install(p['main_jar'], target)
        report['installed']['main'] = str(target)
    runtime.mkdir(parents=True, exist_ok=True)
    if installed_engine.is_file():
        (runtime / 'backups').mkdir(exist_ok=True)
        old_version = engine_version(installed_engine) or 'unknown'
        target = runtime / 'backups' / f'twob2tkit-engine-{old_version}-{stamp}.jar'
        shutil.copyfile(installed_engine, target); report['backups'].append(str(target))
    _install(p['engine_jar'], installed_engine)
    report['installed']['engine'] = str(installed_engine)
    pairs = [(p['engine_jar'], installed_engine)]
    if not engine_only:
        pairs.append((p['main_jar'], game / 'mods' / p['main_jar'].name))
    for source, target in pairs:
        if sha256(source) != sha256(target):
            raise DeployError(f'{target.name} 哈希与构建产物不一致')
    kit_jars = sorted(j.name for j in (game / 'mods').glob('twob2tkit-*.jar'))
    if len(kit_jars) != 1:
        raise DeployError(f'mods 里应只剩一个 Kit 主包，实际：{kit_jars}')
    report['sha256'] = {Path(t).name: sha256(t)[:12] for _, t in pairs}
    report['next'] = ('引擎已更新：游戏内 /twob2tkit reload 生效' if engine_only
                      else '主包已更新：需要完整重启游戏；/twob2tkit reload 不够')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--game-dir', type=Path, default=DEFAULT_GAME)
    parser.add_argument('--engine-only', action='store_true', help='只更新可热加载的引擎')
    parser.add_argument('--dry-run', action='store_true', help='只检查并列出将要做的事')
    args = parser.parse_args(argv)
    try:
        report = deploy(PROJECT, args.game_dir, args.engine_only, args.dry_run)
    except (DeployError, OSError, zipfile.BadZipFile, KeyError) as error:
        print(json.dumps({'ok': False, 'detail': str(error)}, ensure_ascii=False)); return 2
    print(json.dumps({'ok': True, **report}, ensure_ascii=False, indent=1)); return 0


if __name__ == '__main__':
    sys.exit(main())
