"""One journaled native AirPlace wood precursor, followed by normal axe stripping."""
import json,time
from pathlib import Path
from material_plan import inventory_counts
from projection_wood import log_target,cell_at,finish_beams
from owned_air_escape import wait_known_idle


def run_one(client,row,out,checkpoint):
    out=Path(out);out.mkdir(exist_ok=False,parents=True)
    before=checkpoint();key=before['projection_selection']['key'];plan=log_target(row)
    if before.get('projection_air_seed_axis_protocol')!=1 or plan is None or plan['strip']or plan.get('plant'):
        raise RuntimeError('Native axis-aware AirPlace or an exact missing wood target is unavailable')
    raw=plan['raw'];pos=row['pos'];count=inventory_counts(before).get(raw,0)
    if count<1:raise RuntimeError('No carried exact raw wood for air placement')
    book={'target':pos,'projected_state':row['expected'],'raw_state':'Block{'+raw+'}[axis='+plan['axis']+']',
          'world_session':client.world,'task_session':client.task,'complete':False,'pending':None}
    def save():(out/'progress.json').write_text(json.dumps(book,ensure_ascii=False,indent=2))
    save()
    client.checked('select_item',item=raw)
    for _ in range(2):
        checkpoint()
        if cell_at(client,pos)['state']!=row['actual']or inventory_counts(client.status()).get(raw,0)!=count:
            raise RuntimeError('Actual wood cell or carried stock changed before one air placement')
        time.sleep(.2)
    book['pending']='one_native_air_seed';save()
    result=client.request('projection_air_seed',placement_key=key,target=pos,
                          expected_item=raw,expected_state=book['raw_state'])
    (out/'native-air-seed.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    receipt=result.get('projection_air_seed')or{}
    if (result.get('phase')!='done'or receipt.get('server_confirmed')is not True
            or receipt.get('target')!=pos or receipt.get('use_count')!=1
            or receipt.get('expected_state')!=book['raw_state']or receipt.get('projected_state')!=row['expected']
            or receipt.get('requires_stripping')is not True or receipt.get('projection_matches')is not False
            or receipt.get('inventory_before')!=count or receipt.get('inventory_after')!=count-1):
        raise RuntimeError('One air placement is unconfirmed; do not replay or count it as completed projection')
    book['pending']=None;book['raw_placement_confirmed']=True;save()
    if cell_at(client,pos)['state']!=book['raw_state']or inventory_counts(client.status()).get(raw,0)!=count-1:
        raise RuntimeError('Server-confirmed wood precursor changed; retain evidence')
    book['pending']='normal_axe_strip';save()
    finished=finish_beams(client,limit=1,expected_key=key,expected_world=client.world,
                          target_item=row['expected'].split('Block{',1)[1].split('}',1)[0],target_axis=plan['axis'])
    if len(finished['completed'])!=1 or finished['completed'][0]['pos']!=pos:
        raise RuntimeError('The exact air-placed wood was not normally stripped')
    for _ in range(2):
        checkpoint()
        if cell_at(client,pos)['state']!=row['expected']or inventory_counts(client.status()).get(raw,0)!=count-1:
            raise RuntimeError('Final wood state or material count changed after stripping')
        time.sleep(.2)
    book.update(complete=True,pending=None,raw_inventory_before=count,raw_inventory_after=count-1,
                temporary_supports_placed=0,final_state_verified=True)
    save();client.request('snapshot');wait_known_idle(client);return book
