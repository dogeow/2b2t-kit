"""Build only the leaf feature on an explicit immutable installed engine baseline."""
import argparse,hashlib,json,re,subprocess,tempfile,zipfile
from pathlib import Path

def sha(data):return hashlib.sha256(data).hexdigest()
def build(base,expected,classpath,asm,jdk,out,version):
    repo=Path(__file__).resolve().parents[1];data=base.read_bytes()
    if sha(data)!=expected:raise ValueError('Installed baseline hash changed')
    if not re.fullmatch(r'\d+\.\d+\.\d+',version):raise ValueError('Invalid engine version')
    name='dev/twob2tkit/runtime/engine/';default=name+'DefaultTunnelBorerEngine.class'
    with tempfile.TemporaryDirectory(prefix='leaf-overlay-') as directory:
        root=Path(directory);classes=root/'classes';classes.mkdir();original=root/'original.class'
        with zipfile.ZipFile(base) as z:original.write_bytes(z.read(default))
        source=root/'EngineBuildVersion.java';source.write_text('package dev.twob2tkit.runtime.engine; final class EngineBuildVersion { static final String VALUE=version(); static String version(){return "'+version+'";} }\n')
        subprocess.run([str(jdk/'bin/javac'),'-cp',str(base)+':'+classpath.read_text().strip(),'-d',str(classes),
                        str(repo/'src/client/java'/Path(name)/'LeafShearBatch.java'),str(source)],check=True)
        subprocess.run([str(jdk/'bin/javac'),'-cp',str(asm),'-d',str(root),str(repo/'tools/LeafShearHook.java')],check=True)
        patched=root/'patched.class'
        subprocess.run([str(jdk/'bin/java'),'-cp',str(root)+':'+str(asm),'LeafShearHook',str(original),str(patched)],check=True)
        replacements={default:patched.read_bytes(),**{str(p.relative_to(classes)):p.read_bytes()for p in classes.rglob('*.class')}}
        allowed={default,name+'LeafShearBatch.class',name+'EngineBuildVersion.class'}
        if set(replacements)!=allowed:raise ValueError('Unexpected compilation output')
        out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(base) as old,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as new:
            for entry in old.infolist():
                body=old.read(entry.filename)
                if entry.filename=='META-INF/MANIFEST.MF':
                    body=re.sub(rb'twob2tkit-Engine-Version: [^\r\n]+',b'twob2tkit-Engine-Version: '+version.encode(),body)
                new.writestr(entry,replacements.pop(entry.filename,body))
            for key,body in replacements.items():new.writestr(key,body)
        with zipfile.ZipFile(base) as old,zipfile.ZipFile(out) as new:
            changed={p for p in set(old.namelist())|set(new.namelist())if p not in old.namelist() or p not in new.namelist() or old.read(p)!=new.read(p)}
        if changed!=allowed|{'META-INF/MANIFEST.MF'}:raise ValueError('Overlay contains unrelated changes')
        proof={'base_sha256':expected,'sha256':sha(out.read_bytes()),'version':version,'changed_entries':sorted(changed),'source_changes_deployed':'continuous leaf shearing only'}
        out.with_suffix('.json').write_text(json.dumps(proof,indent=2)+'\n');return proof

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--sha256',required=True)
    p.add_argument('--classpath',type=Path,required=True);p.add_argument('--asm',type=Path,required=True)
    p.add_argument('--jdk',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--version',required=True)
    a=p.parse_args();print(json.dumps(build(a.base,a.sha256,a.classpath,a.asm,a.jdk,a.out,a.version),indent=2))
