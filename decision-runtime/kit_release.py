"""Build and atomically install one Kit host jar after Minecraft has exited.

This never launches Minecraft or reads launcher credentials.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


DEFAULT_GAME = Path('/Applications/.minecraft/versions/26.1.2')
JDK = Path('/Users/sam/Code/DogeOW/minecraft-kit/jdk25/Contents/Home')


def version_from_gradle(repo):
    for line in (repo/'gradle.properties').read_text().splitlines():
        if line.startswith('version='):
            return line.partition('=')[2].strip()
    raise RuntimeError('gradle.properties has no version')


def minecraft_running():
    result=subprocess.run(['pgrep', '-f', 'net.fabricmc.loader.impl.launch.knot.KnotClient'],
                          capture_output=True, text=True)
    if result.returncode not in (0,1):
        raise RuntimeError('Cannot determine whether Minecraft is running; installation refused')
    return result.returncode==0


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


def test_totals(repo):
    totals={'tests':0,'failures':0,'errors':0}
    for file in (repo/'build/test-results/test').glob('TEST-*.xml'):
        root=ET.parse(file).getroot()
        for key in totals:totals[key]+=int(root.attrib.get(key,0))
    return totals


def build(repo):
    env=os.environ.copy();env['JAVA_HOME']=str(JDK)
    command=['./gradlew','test','jar','verifyRuntimeEngineJar','--offline']
    process=subprocess.run(command,cwd=repo,env=env,text=True,capture_output=True)
    if process.returncode:
        raise RuntimeError('Build failed:\n'+(process.stdout+'\n'+process.stderr)[-5000:])
    totals=test_totals(repo)
    if totals['tests']<1 or totals['failures'] or totals['errors']:
        raise RuntimeError('Tests did not pass: '+json.dumps(totals))
    return totals


def atomic_bytes(destination,data):
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(prefix='.kit-stage-',suffix='.jar',dir=destination.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        expected=hashlib.sha256(data).hexdigest()
        if sha256(temp)!=expected:raise RuntimeError('Staged jar hash mismatch')
        os.replace(temp,destination)
        if sha256(destination)!=expected:raise RuntimeError('Installed jar hash mismatch')
        return expected
    finally:
        if os.path.exists(temp):os.unlink(temp)


def install(repo,game,version):
    if minecraft_running():raise RuntimeError('Minecraft is still running; save, disconnect and exit first')
    source=repo/'build/libs'/f'twob2tkit-{version}.jar'
    if not source.is_file():raise RuntimeError('Built Kit jar is missing')
    try:
        with zipfile.ZipFile(source) as archive:engine=archive.read('runtime/twob2tkit-engine.jar')
    except (OSError,KeyError,zipfile.BadZipFile) as error:
        raise RuntimeError('Built host must contain its matching runtime engine') from error
    mods=game/'mods';existing=list(mods.glob('twob2tkit-*.jar'))
    if len(existing)!=1:raise RuntimeError('Expected exactly one installed Kit jar')
    old=existing[0];new=mods/source.name;runtime=game/'config/twob2tkit/runtime/twob2tkit-engine.jar'
    expected_engine=hashlib.sha256(engine).hexdigest()
    if old==new and sha256(old)==sha256(source) and runtime.exists() and sha256(runtime)==expected_engine:
        return {'installed':str(new),'sha256':sha256(new),'runtime':str(runtime),'runtime_sha256':expected_engine,'unchanged':True}
    backup=game/'config/twob2tkit/backups'/('before-'+version+'-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(parents=True,exist_ok=False);shutil.copy2(old,backup/old.name)
    config=game/'config/twob2tkit.json'
    if config.is_file():shutil.copy2(config,backup/config.name)
    had_runtime=runtime.exists()
    if had_runtime:shutil.copy2(runtime,backup/runtime.name)
    host_bytes=source.read_bytes()
    if minecraft_running():raise RuntimeError('Minecraft started during staging; installation was not applied')
    try:
        # The external engine is loaded preferentially. Deploy the exact bundled bytes.
        atomic_bytes(runtime,engine);atomic_bytes(new,host_bytes)
        if old!=new:old.unlink()
    except Exception:
        if old==new:atomic_bytes(old,(backup/old.name).read_bytes())
        elif new.exists():new.unlink()
        if had_runtime:atomic_bytes(runtime,(backup/runtime.name).read_bytes())
        elif runtime.exists():runtime.unlink()
        raise
    if len(list(mods.glob('twob2tkit-*.jar')))!=1:raise RuntimeError('More than one Kit jar remains')
    return {'installed':str(new),'sha256':sha256(new),'runtime':str(runtime),
            'runtime_sha256':sha256(runtime),'backup':str(backup)}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,default=DEFAULT_GAME)
    parser.add_argument('--skip-build',action='store_true',help='Use a jar already validated in this run')
    args=parser.parse_args(argv)
    repo=Path(__file__).resolve().parent.parent
    try:
        totals=None if args.skip_build else build(repo)
        result=install(repo,args.game_dir,version_from_gradle(repo))
        if totals is not None:result['tests']=totals
        print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
    except (OSError,RuntimeError,ValueError) as error:
        parser.exit(2,f'kit-release: {error}\n')


if __name__=='__main__':main()
