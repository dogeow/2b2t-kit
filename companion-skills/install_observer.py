#!/usr/bin/env python3
"""Install only this passive skill-memory observer as a macOS user service."""
import json,os,plistlib,subprocess,sys
from pathlib import Path

root=Path(__file__).resolve().parent
state=root/'state';state.mkdir(exist_ok=True)
label='local.sam.minecraft.skill-memory'
plist=Path.home()/'Library/LaunchAgents'/f'{label}.plist'
supervisor=Path.home()/'Library/Application Support/MinecraftCompanion'
args=['/opt/homebrew/bin/python3',str(root/'skillctl.py'),'--state',str(state),'watch',
      '--events',str(supervisor/'events.jsonl'),'--events',str(supervisor/'decisions.jsonl')]
spec={'Label':label,'ProgramArguments':args,'WorkingDirectory':str(root),'RunAtLoad':True,
      'KeepAlive':True,'ThrottleInterval':30,'ProcessType':'Background',
      'StandardOutPath':str(state/'observer.log'),'StandardErrorPath':str(state/'observer.log')}
if plist.exists():
    old=plistlib.loads(plist.read_bytes())
    if old.get('ProgramArguments',[])[1:2]!=[str(root/'skillctl.py')]:raise SystemExit('Existing service belongs to another installation')
    subprocess.run(['launchctl','bootout',f'gui/{os.getuid()}/{label}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
plist.parent.mkdir(parents=True,exist_ok=True);plist.write_bytes(plistlib.dumps(spec))
subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True)
print(json.dumps({'service':label,'read_only':True,'plist':str(plist),'journals':[str(supervisor/'events.jsonl'),str(supervisor/'decisions.jsonl')]},ensure_ascii=False))
