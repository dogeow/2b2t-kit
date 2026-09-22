"""Compare built artifacts before choosing hot reload versus a JVM restart.

The installed main JAR is the baseline, not a dirty Git worktree or an assumed
feature name. Runtime classes and the bundled runtime can change independently.
"""
import hashlib,json,zipfile
from pathlib import Path

def content(jar):
    out={}
    with zipfile.ZipFile(jar) as z:
        for name in z.namelist():
            if name.endswith('/') or name=='META-INF/MANIFEST.MF':continue
            data=z.read(name)
            if name=='fabric.mod.json':
                obj=json.loads(data);obj.pop('version',None);data=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
            out[name]=hashlib.sha256(data).hexdigest()
    return out

def classify(installed,candidate):
    old,new=content(installed),content(candidate)
    changed=sorted(n for n in old.keys()|new.keys() if old.get(n)!=new.get(n))
    runtime=lambda name:name.startswith('dev/twob2tkit/runtime/engine/') or name=='runtime/twob2tkit-engine.jar'
    host=[n for n in changed if not runtime(n)]
    return {'mode':'restart_required' if host else 'hot_reload' if changed else 'unchanged',
            'host_changes':host,'runtime_changes':[n for n in changed if runtime(n)],
            'baseline':str(Path(installed).resolve()),'candidate':str(Path(candidate).resolve())}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('installed');p.add_argument('candidate');a=p.parse_args()
    print(json.dumps(classify(a.installed,a.candidate),ensure_ascii=False,indent=2))
