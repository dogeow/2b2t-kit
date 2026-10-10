"""One owner: wait for standing authorization, restore current field, then full build."""
import argparse
import json
import math
from pathlib import Path
import time
import uuid

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient,Handoff
from material_plan import inventory_counts
from .protocol import JobPaused
from .stationary_resume import StationaryResume
from .navigation import local_park,settled_state,lift_for_travel
from .acquisition import _travel
from .wheat_reconnect_repair import run as restore


class WaitingIntent:
    def __init__(self, request, out):
        self.request=request;self.out=Path(out);self.out.mkdir(exist_ok=True)
        self.context=dict(request['context']);self.state={'state':'paused'}
        self.last_control=request['created_at']-1
    def _validate_resume_context(self, context):return context
    def _event(self, kind, **data):write_json(self.out/'automatic-resume.json',{'kind':kind,**data})


def handoff_can_wait(root, request, error, attempt):
    """Never restart a pending seed use or a foreign/changed-world controller."""
    if not isinstance(error,Handoff) or str(error) not in (
            'Control or world changed; no more commands','User opened a different interface'):
        return False
    state=read_fresh(root);lease=state.get('supervision_lease')or{}
    if (state.get('connected')is not True or state.get('world_session')!=request['context']['world_session']
            or state.get('safety_hold',{}).get('active') or state.get('health',0)<19 or lease):return False
    proof=Path(attempt)/'current-cell-restoration/current-cell-restoration.json'
    if proof.exists() and json.loads(proof.read_text()).get('pending'):return False
    return True


def recover_attempt(root, original, old_journal, pickup_proof, attempt, state):
    attempt=Path(attempt);attempt.mkdir()
    c=None;failure=None;finish_failure=None
    try:
        c=MaterialClient(root,attempt/'control',server=state['server'],remote_finish='guard',
            park_target=[state['pos'][0],min(315,max(90,state['pos'][1]+24)),state['pos'][2]])
        if inventory_counts(c.status()).get('minecraft:wheat_seeds',0)<5:
            from .profile import load
            from material_storage_index import select_sources
            from material_depots import exchange
            profile=load(root,{'server':state['server'],'dimension':state['dimension']})
            route=select_sources(c,profile['depots'],{'minecraft:wheat_seeds':5},reserve_empty=2)
            write_json(attempt/'local-seed-storage-search.json',route)
            if not route['positions']:raise RuntimeError('Registered storage has no available seed reserve')
            staging=profile.get('supply_staging')or profile.get('workbench_staging')
            if staging and min(math.dist(c.status()['pos'],p)for p in route['positions'])>48:
                lift_for_travel(c);_travel(c,staging,lambda:c.status(),[],keep_cruise=True)
            supplied=exchange(c,route['positions'],withdraw={'minecraft:wheat_seeds':5})
            write_json(attempt/'actual-seed-supply.json',supplied)
            if not supplied['complete']:raise RuntimeError('Actual registered seed supply incomplete')
        from .registered_wheat import registered_fields
        from potato_farm import plan
        pending=json.loads(Path(old_journal).read_text()).get('pending')or{}
        field=next((plan(q)for q,_ in registered_fields(c)if pending.get('pos')in plan(q)['cells']),None)
        if field is None:raise RuntimeError('Original harvested cell has no complete field registration')
        center=field['center'];target=[center[0]+.5,max(c.status()['pos'][1],center[1]+24),center[2]+.5]
        if math.hypot(c.status()['pos'][0]-center[0],c.status()['pos'][2]-center[2])>8:
            lift_for_travel(c);_travel(c,target,lambda:c.status(),[],keep_cruise=True)
        if math.dist(c.status()['pos'],[center[0]+.5,center[1]+1.6,center[2]+.5])>3:
            c.checked('navigate',target=[center[0]+.5,center[1]+1.6,center[2]+.5],arrival=.15,air_only=True,seconds=45)
        repaired=restore(c,old_journal,attempt/'current-cell-restoration',pickup_proof=pickup_proof)
        write_json(attempt/'result.json',repaired)
        print('CURRENT_REGISTERED_FIELD_CONFIRMED',repaired.get('new_reseed'),flush=True)
    except Exception as error:
        failure=error;write_json(attempt/'error.json',{'type':type(error).__name__,'detail':str(error),'old_journals_preserved':True})
    finally:
        if c is not None:
            try:
                # A manual handoff has already released the old native owner.
                c.status()
                point=local_park(c);c.checked('navigate',target=point,arrival=.25,air_only=True,seconds=90)
                q=settled_state(c,point,.55);point=[q['pos'][0],q['pos'][1]+1,q['pos'][2]]
                c.checked('material_job_park',park_target=point);c.park_target=point
                if c.finish()is False:raise RuntimeError('Original recovery parking not confirmed')
            except Handoff as error:
                c.heartbeat.close();finish_failure=error
            except Exception as error:
                write_json(attempt/'finish-waiting.json',{'detail':str(error),'world_session':c.world,
                    'task_session':c.task,'lease_id':c.heartbeat.id,'no_new_controller':True})
                print('RECOVERY_FINISH_WAITING',str(error),flush=True)
                while True:
                    try:
                        q=c.status()
                        if(q.get('supervision_lease')or{}).get('id')!=c.heartbeat.id:raise Handoff('Original owner changed')
                    except Handoff as changed:
                        c.heartbeat.close();finish_failure=changed;break
                    time.sleep(.5)
    if failure is not None:raise failure
    if finish_failure is not None:raise finish_failure
    return c.task


def run(root, original, old_journal, pickup_proof, out):
    root=Path(root);out=Path(out);out.mkdir(exist_ok=False)
    state=read_fresh(root)
    if (state.get('connected')is not True or state.get('server','').removesuffix(':25565')!=original['context']['server'].removesuffix(':25565')
            or state.get('dimension')!=original['context']['dimension']
            or state.get('projection_selection',{}).get('key')!=original['projection_key']):
        raise RuntimeError('Current server, dimension or full projection differs; no controller created')
    original={**original,'created_at':int(time.time()*1000),'context':{**original['context'],
        'world_session':state['world_session'],'expected_revision':state['control_revision'],'start_pos':state['pos']}}
    waiting=WaitingIntent(original,out/'waiting');watch=StationaryResume(root);number=0
    parked=state.get('supervision_lease')or{}
    if parked.get('kind')=='parking'and parked.get('world_session')==state['world_session']:
        waiting.state['native_task_session']=parked.get('job_session')
    while True:
        if(out/'cancel-wait-only.json').exists():
            result={'phase':'cancelled','game_actions_dispatched':number>0};write_json(out/'result.json',result);return result
        state=read_fresh(root)
        if state.get('world_session')!=original['context']['world_session']:
            result={'phase':'waiting','reason':'world_changed','automatic_old_action_replay':False};write_json(out/'result.json',result);return result
        held=inventory_counts(state)if state.get('inventory')else{}
        if (state.get('food',0)<18 or any(state.get(k)for k in ('printing','planter_active','feeder_active','fisher_active'))):
            watch.reset();time.sleep(.25);continue
        if not watch.poll(waiting):time.sleep(.25);continue
        state=read_fresh(root)
        number+=1;attempt=out/('attempt-%03d'%number)
        write_json(out/'state.json',{'phase':'restoring_current_field','attempt':number,'world_session':state['world_session']})
        try:recovery_task=recover_attempt(root,original,old_journal,pickup_proof,attempt,state)
        except Exception as error:
            if handoff_can_wait(root,original,error,attempt):
                watch.reset();waiting.state={'state':'paused'}
                write_json(out/'state.json',{'phase':'waiting_after_manual_handoff','attempt':number,'original_pending_replayed':False})
                continue
            write_json(out/'result.json',{'phase':'blocked','detail':str(error),'type':type(error).__name__,'old_journals_preserved':True});raise
        break
    from material_jobs_cli import serve
    from projection_flat_backend import create_backend
    waiting.state={'state':'paused','native_task_session':recovery_task};watch.reset()
    while not watch.poll(waiting):
        state=read_fresh(root)
        if state.get('world_session')!=original['context']['world_session']:
            raise JobPaused('世界已改变，当前恢复证据已保存')
        time.sleep(.25)
    state=read_fresh(root)
    request={**original,'id':'full-map-kit-'+uuid.uuid4().hex[:12],'created_at':int(time.time()*1000),
             'context':{**original['context'],'world_session':state['world_session'],'expected_revision':state['control_revision'],'start_pos':state['pos']}}
    write_json(out/'request.json',request)
    result=serve(request,root,out/'material-job',create_backend);write_json(out/'result.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('automation','request','old-journal','pickup-proof','out'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();original=json.loads(args.request.read_text())
    result=run(args.automation,original,args.old_journal,args.pickup_proof,args.out)
    return 0 if result.get('state')in('completed','paused','cancelled')or result.get('phase')=='cancelled'else 2


if __name__=='__main__':raise SystemExit(main())
