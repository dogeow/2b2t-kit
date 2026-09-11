#!/usr/bin/env python3
"""Install the user's local event supervisor. Does not touch Minecraft or Codex credentials."""
import json,os,plistlib,subprocess,sys,time
from pathlib import Path
from companion import DEFAULT

LABEL='local.sam.minecraft-companion'
STATE=Path.home()/'Library/Application Support/MinecraftCompanion'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'

def main():
    if sys.platform!='darwin':raise SystemExit('This installer targets macOS launchd; companion.py also runs in foreground')
    script=Path(__file__).resolve().with_name('companion.py');STATE.mkdir(parents=True,exist_ok=True);(STATE/'logs').mkdir(exist_ok=True)
    config=STATE/'config.json'
    if not config.exists():config.write_text(json.dumps(DEFAULT,ensure_ascii=False,indent=2))
    config.chmod(0o600)
    obj={'Label':LABEL,'ProgramArguments':[sys.executable,str(script),'run','--state-dir',str(STATE),'--config',str(config)],'WorkingDirectory':str(script.parent),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,'ProcessType':'Background','StandardOutPath':str(STATE/'logs/service.stdout.log'),'StandardErrorPath':str(STATE/'logs/service.stderr.log')}
    PLIST.parent.mkdir(parents=True,exist_ok=True)
    if PLIST.exists():
        old=plistlib.loads(PLIST.read_bytes())
        if 'MinecraftCompanion' not in ' '.join(old.get('ProgramArguments',[])):raise SystemExit('Existing service is not owned by this installer')
        (STATE/f'launch-agent-before-{int(time.time())}.plist').write_bytes(PLIST.read_bytes())
        subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}',str(PLIST)],capture_output=True)
    PLIST.write_bytes(plistlib.dumps(obj));PLIST.chmod(0o600)
    subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(PLIST)],check=True)
    print(json.dumps({'installed':True,'label':LABEL,'state':str(STATE),'script':str(script),'mode':'event-driven diagnosis; no game commands'},ensure_ascii=False))
if __name__=='__main__':main()
