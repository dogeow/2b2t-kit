"""Bring verified natural dark oak saplings home without consuming them in replanting."""
import argparse,json,math,time
from pathlib import Path
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from drop_collection import collect_drop
from . import bobby_snow_cache as cache,bobby_snow_route as route
from .acquisition import block_id,_travel
from .navigation import lift_for_travel,local_park,settled_state
from .resource_tree_trip import current_tree_region,BIOMES
from .profile import load

ITEM='minecraft:dark_oak_sapling'

def natural_leaf(row):
    return (isinstance(row,dict) and block_id(row)=='minecraft:dark_oak_leaves'
            and 'persistent=false' in row.get('state','') and 'waterlogged=false' in row.get('state','')
            and row.get('fluid') is False and row.get('block_entity') is False)

def harvest_hoe(state):
    choices=[r for r in state.get('inventory',[]) if r.get('item')=='minecraft:diamond_hoe'
             and r.get('count')==1 and r.get('durability',0)>=33
             and not any(e.get('id')=='minecraft:silk_touch' for e in r.get('enchantments',[]))]
    if not choices:raise RuntimeError('Sapling collection requires a verified non-Silk-Touch diamond hoe')
    return max(choices,key=lambda r:r['durability'])

def run(root,request,candidate,out,target=4):
    root=Path(root);out=Path(out);out.mkdir(exist_ok=False);first=read_fresh(root)
    if (first['projection_selection']['key']!=request['projection_key'] or first['health']!=20
            or first.get('food',0)<18 or first.get('screen') or first.get('manual_movement')):
        raise RuntimeError('Current full map or healthy control changed')
    harvest_hoe(first)
    if room_for_item(first,ITEM)<target:raise RuntimeError('No verified room for saplings')
    wanted=BIOMES['dark_oak'];game=root.parents[2]
    if not cache.validate_candidate(game,first['server'],first['dimension'],candidate,biome_filter=wanted):
        raise RuntimeError('Current forest hint changed')
    c=MaterialClient(root,out/'control',first['server'],remote_finish='guard',
                     park_target=[first['pos'][0],min(315,max(160,first['pos'][1]+24)),first['pos'][2]])
    book={'world_session':c.world,'item':ITEM,'target':target,'mined':[],
          'returned_home':False,'map_complete':False};ledger={};path=out/'resource-route.json'
    settled=True
    def checkpoint():
        s=c.status()
        if (s['health']<19 or s.get('food',0)<18 or s['projection_selection']['key']!=request['projection_key']):
            raise RuntimeError('Healthy sapling trip or complete map scope changed')
        return s
    def count():return inventory_counts(checkpoint()).get(ITEM,0)
    def pickup():
        for _ in range(12):
            s=checkpoint();drop=next((e for e in s.get('entities',[]) if e.get('type')=='minecraft:item'
                and e.get('stack',{}).get('item')==ITEM
                and all(abs(e['pos'][i]-candidate['target'][i])<70 for i in (0,2))),None)
            if not drop:return
            if not collect_drop(c,drop,seconds=45):raise RuntimeError('Sapling pickup is unconfirmed; no repeated movement')
    def mine(pos,expected):
        nonlocal settled
        tool=harvest_hoe(checkpoint())
        if c.status().get('selected_slot')!=tool['slot']:
            c.checked('select_item',item='minecraft:diamond_hoe',slot=tool['slot'])
        write_json(out/'pending.json',{'pos':pos,'expected_state':expected,'world_session':c.world,'before':count()})
        settled=False
        r=c.checked('mine_block',pos=pos,face='up',expected_state=expected,seconds=20)
        settled=True;book['mined'].append({'pos':pos,'request_id':r['id'],'server_confirmation':r.get('server_confirmation')})
        write_json(out/'progress.json',book);time.sleep(.2);pickup()
        print('ACTUAL_SAPLINGS',count(),flush=True)
    try:
        c.set_progress(phase='收集带回岛内种树的树苗')
        lift_for_travel(c)
        route.outbound(c,candidate,first['server'],first['dimension'],path,ledger,checkpoint,
            lambda v:cache.validate_candidate(game,first['server'],first['dimension'],v,biome_filter=wanted),
            lambda v:cache.validate_current_world(game,first['server'],first['dimension'],v))
        survey=c.request('scan_trees',item='minecraft:dark_oak_log',radius=96)
        profile=load(root,checkpoint());current_tree_region(survey,c.world,c.last,'minecraft:dark_oak_log',candidate,
            list(profile.get('protected_regions',[]))+[first['projection_selection']])
        write_json(out/'tree-survey.json',survey);route.mark_harvesting(c,path,json.loads(path.read_text()))
        x,z=candidate['tile'];scan=c.checked('scan',min=[x-8,72,z-8],max=[x+23,117,z+23],details=True)
        write_json(out/'natural-leaves.json',scan)
        leaves=[r for r in scan['blocks'] if natural_leaf(r)]
        leaves.sort(key=lambda r:(-r['pos'][1],sum((r['pos'][i]-candidate['target'][i])**2 for i in (0,2))))
        for row in leaves[:256]:
            if count()>=target:break
            pos=row['pos'];fresh=c.checked('scan',min=pos,max=pos,details=True)['blocks']
            if len(fresh)!=1 or not natural_leaf(fresh[0]):continue
            pose=[pos[0]+.5,pos[1]+2.2,pos[2]+.5]
            _travel(c,pose,checkpoint,[])
            fresh=c.checked('scan',min=pos,max=pos,details=True)['blocks']
            if len(fresh)!=1 or not natural_leaf(fresh[0]):continue
            mine(pos,fresh[0]['state'])
        if count()<target:raise RuntimeError('Bounded natural leaf batch ended before four carried saplings')
        book['forest_stock']=count();lift_for_travel(c);route.return_home(c,checkpoint,reason='verified_saplings_for_island')
        book.update(returned_home=True,return_stock=count());write_json(out/'result.json',book)
        print('SAPLINGS_RETURNED_HOME',book['return_stock'],flush=True)
    except Exception as error:
        book.update(error=str(error),unresolved_mutation=not settled);write_json(out/'result.json',book);raise
    finally:
        try:
            if settled and c.native_inflight is None and not getattr(c,'unconfirmed_native_request',None):
                point=local_park(c);c.checked('navigate',target=point,arrival=.25,air_only=True,seconds=90)
                s=settled_state(c,point,.55);c.park_target=[s['pos'][0],s['pos'][1]+1,s['pos'][2]]
                c.checked('material_job_park',park_target=c.park_target)
            else:
                s=c.status(wait_interface=False);c.park_target=[s['pos'][0],min(315,s['pos'][1]+48),s['pos'][2]]
        finally:c.finish()
    return book

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('automation','request','candidates','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.automation,json.loads(a.request.read_text()),json.loads(a.candidates.read_text())[0],a.out)

if __name__=='__main__':main()
