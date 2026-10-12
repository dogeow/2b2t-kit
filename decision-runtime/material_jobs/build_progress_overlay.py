"""Enrich only an existing older worker's HUD; never owns controls or edits task journals."""
import argparse,json,os,time
from pathlib import Path
from .build_progress import BuildMaterialProgress,phase
from .progress import ItemNames,quantities_summary


def overlay(request,root,out,reader,name):
    state=reader.read(root/'status.json');status=reader.read(out/'status.json')
    if status.get('terminal') or state.get('world_session')!=request['context']['world_session']:return False
    lease=state.get('supervision_lease')or{};now=int(time.time()*1000)
    if (state.get('connected')is not True or state.get('manual_movement') is not False
            or status.get('id')!=request['id'] or lease.get('kind')!='materials'
            or lease.get('world_session')!=state.get('world_session')
            or lease.get('job_session')!=status.get('native_task_session')
            or lease.get('revision')!=state.get('control_revision')
            or not 0<=now-state.get('time',0)<=3000 or not 0<=now-status.get('updated_at',0)<=5000):return True
    detail=reader.details(request,status,state,out)
    if detail is None:return True
    target=root/'job-progress.json';original=target.read_bytes();payload=json.loads(original)
    if (payload.get('task_session')!=lease['job_session']
            or payload.get('world_session')!=state['world_session']
            or payload.get('control_revision')!=state['control_revision']):return True
    pending=reader.read(out/'inflight.json')if(out/'inflight.json').exists()else None
    legacy=quantities_summary(request,status,pending,state,name)
    displayed=(payload.get('title'),payload.get('done'),payload.get('total'))
    enhanced=('地图',detail['map_done'],detail['map_total'])
    if displayed!=enhanced and (legacy is None or displayed!=legacy[:3]):return True
    text=phase(detail,name)
    if payload.get('phase')==text:return True
    payload.update(title=enhanced[0],done=enhanced[1],total=enhanced[2],phase=text,current_material=detail)
    temporary=target.with_suffix('.build-details.tmp')
    try:
        temporary.write_text(json.dumps(payload,ensure_ascii=False))
        # Keep the owner's title, counters, revision and freshness timestamp.
        if target.read_bytes()==original:os.replace(temporary,target)
    finally:temporary.unlink(missing_ok=True)
    return True


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('automation','request','out'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();request=json.loads(args.request.read_text());reader=BuildMaterialProgress(args.automation);name=ItemNames(args.automation)
    while True:
        try:
            if not overlay(request,args.automation,args.out,reader,name):return
        except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
        time.sleep(.025)

if __name__=='__main__':main()
