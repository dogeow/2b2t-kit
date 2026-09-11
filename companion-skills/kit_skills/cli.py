import argparse,json,time,os,fcntl,signal
from pathlib import Path
from .library import SkillManager
from .catalog import export_catalog
from .planning import goal_request,compile_plan
from .model import resolve,validate_action
from .learning import propose_from_ai,learn_episode
from .kit import KitRecorder,ingest_supervisor,read_json

def emit(value):print(json.dumps(value,ensure_ascii=False,indent=2),flush=True)
def compile_skill(manager,name,params):
    row=manager.get(name)
    if row['status']!='verified':raise ValueError('Skill has not passed repeated objective verification')
    skill=row['skill'];missing=set(skill.get('parameters',{}))-set(params)
    if missing:raise ValueError('Missing parameters: '+','.join(sorted(missing)))
    steps=resolve(skill['steps'],params)
    for s in steps:validate_action(s['op'],s['args'])
    return {'skill':name,'version':row['version'],'steps':steps,'preconditions':skill.get('preconditions',{}),'success':resolve(skill['success'],params),'dispatch':'existing Kit controller','note':'Compiled only. No action mailbox was written.'}
def main():
    p=argparse.ArgumentParser(description='Voyager-style skill memory for Minecraft Kit')
    p.add_argument('--state',default=str(Path(__file__).resolve().parents[1]/'state'))
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('status')
    sub.add_parser('export-catalog')
    q=sub.add_parser('lessons');q.add_argument('query',nargs='?',default='')
    q=sub.add_parser('plan-request');q.add_argument('goal');q.add_argument('--snapshot',required=True)
    q=sub.add_parser('check-plan');q.add_argument('file')
    q=sub.add_parser('retrieve');q.add_argument('query');q.add_argument('--candidates',action='store_true')
    q=sub.add_parser('propose');q.add_argument('file')
    q=sub.add_parser('learn');q.add_argument('file')
    q=sub.add_parser('compile');q.add_argument('name');q.add_argument('--parameters',default='{}')
    q=sub.add_parser('ingest-events');q.add_argument('file')
    for cmd in ('inspect','watch'):
        q=sub.add_parser(cmd);q.add_argument('--automation',default='/Applications/.minecraft/config/twob2tkit/automation')
        if cmd=='watch':q.add_argument('--seconds',type=int,default=0);q.add_argument('--events',action='append',default=[])
    a=p.parse_args();m=SkillManager(a.state)
    try:
        if a.cmd=='status':emit(m.summary())
        elif a.cmd=='export-catalog':emit({'exported_skills':export_catalog(m)})
        elif a.cmd=='lessons':emit(m.recent_lessons(a.query,5))
        elif a.cmd=='plan-request':emit(goal_request(m,a.goal,read_json(a.snapshot)))
        elif a.cmd=='check-plan':emit(compile_plan(m,read_json(a.file)))
        elif a.cmd=='retrieve':emit(m.retrieve_skills(a.query,a.candidates))
        elif a.cmd=='propose':emit(propose_from_ai(m,read_json(a.file)))
        elif a.cmd=='learn':emit(learn_episode(m,read_json(a.file)))
        elif a.cmd=='compile':emit(compile_skill(m,a.name,json.loads(a.parameters)))
        elif a.cmd=='ingest-events':emit({'ingested':ingest_supervisor(m,a.file),**m.summary()})
        else:
            r=KitRecorder(a.automation,m)
            if a.cmd=='inspect':emit(r.snapshot());return
            lock=Path(a.state)/'observer.lock'
            with lock.open('w') as f:
                fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);f.write(str(os.getpid()));f.flush()
                started=time.monotonic();running=True;next_export=0
                def stop(*_):nonlocal running;running=False
                signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
                while running and (not a.seconds or time.monotonic()-started<a.seconds):
                    try:
                        for event in r.poll():emit(event)
                        for journal in a.events:
                            if Path(journal).exists():ingest_supervisor(m,journal)
                    except (FileNotFoundError,json.JSONDecodeError,ValueError):pass
                    beat={'pid':os.getpid(),'time':time.time(),'read_only':True,'game_heartbeat_age_seconds':None if r.previous is None else round(time.time()-r.previous.get('time',0)/1000,2),**m.summary()}
                    fpath=Path(a.state)/'observer-status.json';tmp=fpath.with_suffix('.tmp');tmp.write_text(json.dumps(beat));tmp.replace(fpath)
                    if time.monotonic()>=next_export:
                        export_catalog(m);next_export=time.monotonic()+2
                    time.sleep(.5)
                fpath=Path(a.state)/'observer-status.json';fpath.write_text(json.dumps({'pid':None,'time':time.time(),'stopped':True}))
    finally:m.close()
if __name__=='__main__':main()
