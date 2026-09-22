"""Install a verified local engine and reload through the native bridge without UI or JVM restart."""
from pathlib import Path
import hashlib,json,shutil,time,zipfile

def inspect_engine(jar):
    jar=Path(jar)
    with zipfile.ZipFile(jar) as archive:
        names=set(archive.namelist())
        if any(n.startswith('dev/twob2tkit/runtime/api/') for n in names):raise ValueError('Stable API must remain in the main mod')
        if 'dev/twob2tkit/runtime/engine/DefaultBuildNavigation.class' not in names:raise ValueError('Missing navigation engine')
        props={}
        for line in archive.read('META-INF/MANIFEST.MF').decode().splitlines():
            if ': ' in line:
                k,v=line.split(': ',1);props[k]=v
    return {'version':props['twob2tkit-Engine-Version'],'host_api':int(props['twob2tkit-Host-API']),
            'sha256':hashlib.sha256(jar.read_bytes()).hexdigest()}

def install_and_reload(client,jar):
    jar=Path(jar);artifact=inspect_engine(jar);before=client.status()
    if before.get('runtime_reload_protocol',0)<1 or before.get('runtime_host_api',0)<artifact['host_api']:
        raise RuntimeError('This host needs a full update before it can hot reload this engine')
    if before.get('health',0)<19 or before.get('screen') or before.get('safety_hold',{}).get('active'):
        raise RuntimeError('Wait for healthy idle control before updating')
    runtime=client.root.parent/'runtime';runtime.mkdir(exist_ok=True)
    installed=runtime/'twob2tkit-engine.jar';backup=runtime/'backups'/('hot-'+str(time.time_ns())+'.jar');backup.parent.mkdir(exist_ok=True)
    if installed.exists():shutil.copy2(installed,backup)
    staged=installed.with_suffix('.jar.installing');shutil.copy2(jar,staged)
    if hashlib.sha256(staged.read_bytes()).hexdigest()!=artifact['sha256']:raise RuntimeError('Staged engine hash mismatch')
    staged.replace(installed)
    try:
        reply=client.checked('runtime_reload')
        # Use the acknowledged reply, not a potentially lagging periodic status file.
        if reply.get('runtime_version')!=artifact['version'] or reply.get('navigation_runtime_version')!=artifact['version']:
            raise RuntimeError('Runtime version was not confirmed; do not repeat reload blindly')
        if reply.get('world_session')!=before.get('world_session') or reply.get('runtime_generation')!=before.get('runtime_generation',0)+1:
            raise RuntimeError('Hot reload continuity was not confirmed')
        old_job=before.get('build_job',{});new_job=reply.get('build_job',{})
        if old_job.get('active') and (not new_job.get('active') or old_job.get('session')!=new_job.get('session')):
            raise RuntimeError('Construction task was not retained')
    except Exception:
        # Restore the on-disk fallback; never send an uncertain reload a second time.
        if backup.exists():
            shutil.copy2(backup,staged);staged.replace(installed)
        raise
    proof={**artifact,'before_generation':before.get('runtime_generation',0),'after_generation':reply['runtime_generation'],
           'world_session':reply['world_session'],'build_session':reply.get('build_job',{}).get('session'),
           'connected':reply.get('connected'),'health':reply.get('health'),'backup':str(backup) if backup.exists() else None}
    (client.out/'hot-update-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print('HOT_UPDATED',artifact['version'],'generation',proof['after_generation'],flush=True)
    return proof
