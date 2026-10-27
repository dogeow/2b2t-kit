"""Observe ordinary shallow ascents; only the native budget can admit deeper work."""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from .acquisition import block_id

def calibrate(c,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);path=out/'calibration.json';q=checkpoint();x,_,z=q['pos']
    if q.get('under_water')or not q.get('auto_log')or q.get('health')!=20 or q.get('air_supply')!=q.get('max_air_supply',300):raise RuntimeError('Healthy full-air guarded surface required')
    book={'world_session':c.world,'pos':[x,z],'cycles':[],'pending':None,'complete':False,'safety_floors_changed':False};write_json(path,book)
    def point(y):return [x,float(y),z]
    def water_scan():
        low=[math.floor(x-.31),58,math.floor(z-.31)];high=[math.floor(x+.31),62,math.floor(z+.31)]
        r=c.request('scan',min=low,max=high,details=True)
        water={'minecraft:water','minecraft:kelp','minecraft:kelp_plant','minecraft:seagrass','minecraft:tall_seagrass'}
        total=math.prod(b-a+1 for a,b in zip(low,high))
        if(r.get('phase')!='done'or r.get('scan_cells_read')!=total or len(r.get('blocks',[]))!=total or any(block_id(v)not in water or v.get('block_entity')for v in r['blocks'])):raise RuntimeError('Calibration requires a currently clear shallow water column')
    def move(op,target,label,**kw):
        checkpoint();book['pending']={'kind':label,'target':target};write_json(path,book)
        try:r=c.checked(op,target=target,seconds=20,**kw)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        write_json(out/('%02d-%s-native.json'%(len(book['cycles']),label)),r);book['pending']=None;write_json(path,book)
    water_scan();native_observed=False
    for i in range(5):
        q=checkpoint()
        if q.get('under_water')or q.get('air_supply')!=q.get('max_air_supply',300):raise RuntimeError('Prior calibration breath not replenished')
        move('navigate',point(63.2),'surface-entry-pose',arrival=.15,air_only=True)
        move('walk',point(60),'ordinary-shallow-entry',arrival=.25,restore_flight=True)
        q=checkpoint()
        if not q.get('under_water')or q.get('air_supply',0)<260:raise RuntimeError('Healthy shallow water entry unconfirmed')
        c.checked('air_return_set',target=point(65));q=checkpoint()
        if q.get('air_budget_source')=='observed'and q.get('air_budget_samples',0)>=3:
            native_observed=True;book['native_observed_budget']={k:q.get(k)for k in('time','air_budget_source','air_budget_samples','air_return_floor','air_work_floor','air_budget_valid_until')}
        if not native_observed:
            water_scan();move('navigate',point(58),'bounded-shallow-descent',arrival=.2)
            c.checked('air_return_set',target=point(65))
        submerged=checkpoint();move('navigate',point(65),'normal-vertical-ascent',arrival=.2)
        until=time.monotonic()+4
        while True:
            q=checkpoint()
            if not q.get('under_water')and q.get('air_supply')==q.get('max_air_supply',300):break
            if time.monotonic()>until:raise RuntimeError('Native calibration ascent did not replenish actual air')
            time.sleep(.1)
        book['cycles'].append({'index':i,'submerged':{k:submerged.get(k)for k in('time','pos','air_supply','air_budget_source')},'surface':{k:q.get(k)for k in('time','pos','health','air_supply')},'native_observed_budget_seen':native_observed});write_json(path,book)
        if native_observed:book['complete']=True;write_json(path,book);return book
    raise RuntimeError('Native ascent samples did not qualify; never lower oxygen floors')
