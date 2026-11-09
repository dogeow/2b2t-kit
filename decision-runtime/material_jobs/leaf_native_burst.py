"""One bounded game-side shearing burst; no per-leaf bridge round trips."""
import json,time,uuid
from pathlib import Path
from kit_runtime.journal import write_json


def execute(client,rows,directory,checkpoint,record):
    state=checkpoint();lease=state.get('supervision_lease') or {}
    if (not 1<=len(rows)<=32 or lease.get('job_session')!=client.task or lease.get('id')!=client.heartbeat.id
            or lease.get('world_session')!=client.world or lease.get('revision')!=state.get('control_revision')
            or state.get('native_material_busy') or state.get('pending_scan') or state.get('navigating')):
        raise RuntimeError('Native leaf burst does not own an idle material station')
    request={'protocol':1,'id':'leaf-'+uuid.uuid4().hex[:20],'world_session':client.world,
             'server':state['server'],'dimension':state['dimension'],'player_uuid':state['player_uuid'],
             'input_serial':state['game_interaction']['interaction_serial'],
             'task_session':client.task,'lease_id':client.heartbeat.id,'expected_revision':state['control_revision'],
             'issued_at':int(time.time()*1000),'expires_at':int(time.time()*1000)+15000,
             'targets':[{'pos':r['pos'],'item':r['state'].split('}',1)[0].removeprefix('Block{')}for r in rows]}
    out=Path(directory)/request['id'];out.mkdir(parents=True,exist_ok=False)
    write_json(out/'intent.json',request);record(request)
    client.native_leaf_pending=request
    write_json(client.root/'leaf-shear-request.json',request)
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        actual=checkpoint()
        try:receipt=json.loads((client.root/'leaf-shear-state.json').read_text())
        except (OSError,ValueError):receipt={}
        if receipt.get('id')==request['id'] and receipt.get('phase') in ('done','stopped','waiting'):
            write_json(out/'native-result.json',receipt)
            scope=all(receipt.get(k)==request[k] for k in ('world_session','task_session','lease_id','expected_revision'))
            expected={tuple(r['pos']):r['item'] for r in request['targets']};seen=set()
            settled=(receipt.get('phase')=='done' or receipt.get('phase')=='stopped' and receipt.get('reason')=='shears_changed_or_exhausted'
                     or receipt.get('phase')=='waiting' and receipt.get('reason')=='vanilla_predictions_unsettled')
            valid=(settled and scope and actual.get('world_session')==client.world and actual.get('control_revision')==request['expected_revision']
                   and receipt.get('protocol')==1 and receipt.get('execution')=='native_continuous_shears_v1'
                   and receipt.get('confirmation')=='vanilla_prediction_retired_and_live_block_observation'
                   and receipt.get('pending')==[] and type(receipt.get('attempted')) is int
                   and 0<=receipt['attempted']<=len(request['targets'])
                   and receipt['attempted']>=len(receipt.get('removed',[])))
            for key in ('removed','remaining'):
                if not isinstance(receipt.get(key),list):valid=False;continue
                for row in receipt[key]:
                    p=tuple(row.get('pos',[]))
                    if p not in expected or p in seen or row.get('item')!=expected.get(p):valid=False
                    if key=='removed' and row.get('state') not in ('Block{minecraft:air}','Block{minecraft:cave_air}','Block{minecraft:void_air}'):valid=False
                    seen.add(p)
            if not valid:raise RuntimeError('Original leaf burst is unsettled or scope changed; no replay')
            client.native_leaf_pending=None
            return receipt
        time.sleep(.05)
    raise RuntimeError('Original leaf burst result unknown; preserve identity without replay')
