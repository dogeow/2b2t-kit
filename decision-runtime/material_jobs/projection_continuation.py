"""Continue one full projection after manual input without replaying old leaf journals."""
import argparse
import json
from pathlib import Path
import time
import uuid

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from .stationary_resume import StationaryResume
from .recovery_continuation import WaitingIntent


MANUAL_FAILURES={'Control revision changed outside the owned request',
                 'Control or world changed; no more commands'}


def can_continue_after_manual(root,world,result):
    early_handoff=(result.get('state')=='blocked'and result.get('detail')=='Control or world changed; no more commands'
                   and result.get('steps')==0 and result.get('work_detail_before_finish')in
                   ('Meteor Flight 已关闭，区域飞行已停止','Control or world changed; no more commands'))
    if result.get('state')not in ('failed','cancelled','paused')and not early_handoff:return False
    if result.get('detail')not in MANUAL_FAILURES:return False
    state=read_fresh(root)
    return (state.get('connected')is True and state.get('world_session')==world
            and state.get('health',0)>=19 and not state.get('safety_hold',{}).get('active')
            and not state.get('supervision_lease'))


def run(root,original,out):
    from material_jobs_cli import serve
    from projection_flat_backend import create_backend
    root=Path(root);out=Path(out);out.mkdir(exist_ok=False)
    first=read_fresh(root);world=first['world_session']
    if (not first.get('connected')or first.get('projection_selection',{}).get('key')!=original['projection_key']
            or first.get('server','').removesuffix(':25565')!=original['context']['server'].removesuffix(':25565')
            or first.get('dimension')!=original['context']['dimension']):raise ValueError('Current full goal scope differs')
    original={**original,'created_at':int(time.time()*1000),'context':{**original['context'],
        'world_session':world,'expected_revision':first['control_revision'],'start_pos':first['pos']}}
    waiting=WaitingIntent(original,out/'waiting');watch=StationaryResume(root);attempt=0;previous=None
    while True:
        while not watch.poll(waiting):
            state=read_fresh(root)
            if state.get('world_session')!=world:
                result={'state':'blocked','detail':'World changed; original receipts retained','terminal':True}
                write_json(out/'result.json',result);return result
            if(out/'cancel-wait-only.json').exists():
                result={'state':'cancelled','detail':'Waiter stopped before new control','terminal':True}
                write_json(out/'result.json',result);return result
            time.sleep(.25)
        state=read_fresh(root);attempt+=1;directory=out/('attempt-%03d'%attempt);directory.mkdir()
        request={**original,'id':'full-map-kit-'+uuid.uuid4().hex[:12],'created_at':int(time.time()*1000),
                 'context':{**original['context'],'expected_revision':state['control_revision'],'start_pos':state['pos']}}
        write_json(directory/'request.json',request)
        write_json(directory/'independent-current-intent.json',{'previous_attempt':previous,
            'old_pending_receipts_reclassified':False,'old_leaf_journal_replayed':False,
            'requires_new_complete_projection_audit':True})
        write_json(out/'state.json',{'phase':'full_projection_running','attempt':attempt,'job_id':request['id'],
                                   'job_directory':str(directory/'material-job')})
        result=serve(request,root,directory/'material-job',create_backend)
        write_json(directory/'result.json',result)
        if not can_continue_after_manual(root,world,result):
            write_json(out/'result.json',result);return result
        previous=str(directory/'material-job');watch.reset();waiting.state={'state':'paused'}
        write_json(out/'state.json',{'phase':'waiting_after_manual_input','attempt':attempt,
            'original_partial_leaf_receipts_retained':True,'automatic_old_action_replay':False})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('automation','request','out'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();result=run(args.automation,json.loads(args.request.read_text()),args.out)
    return 0 if result.get('state')in('completed','paused','cancelled')else 2


if __name__=='__main__':raise SystemExit(main())
