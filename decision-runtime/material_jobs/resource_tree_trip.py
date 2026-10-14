"""One explicit cached-biome tree trip, real harvest, confirmed home, then map.

Reuses the existing Bobby segment/return ledger and the existing native wood
acquisition. A cached forest is only a travel hint; real roots and fresh natural
terrain scans must authorize each harvest. Never replays an uncertain segment.
"""
import argparse
import json
import math
import time
from pathlib import Path

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient
from material_plan import inventory_counts
from material_trip_policy import room_for_item
from . import bobby_snow_cache as cache, bobby_snow_route as route
from .acquisition import acquire
from .navigation import lift_for_travel,local_park,settled_state
from .profile import load
from .projection_continuation import run as continue_projection

BIOMES={'dark_oak':{'minecraft:dark_forest'},
        'spruce':{'minecraft:taiga','minecraft:old_growth_spruce_taiga','minecraft:old_growth_pine_taiga',
                  'minecraft:snowy_taiga','minecraft:grove'}}


def platform_input_ready(state):
    return any(set(r)=={'slot','item','count','max_stack'}and type(r['slot'])is int and 0<=r['slot']<36
               and r['item']=='minecraft:dirt'and type(r['count'])is int and r['count']>=1
               for r in state.get('inventory',[]))


def current_tree_region(reply, world, request_id, item, candidate, protected):
    survey=reply.get('tree_survey')or{}
    if (reply.get('phase')not in(None,'done')or reply.get('world_session')!=world
            or reply.get('id')!=request_id or not isinstance(survey.get('trees'),list)
            or survey.get('loaded_columns',0)<9000):
        raise RuntimeError('Current forest observation is incomplete')
    x,z=candidate['tile'];low=[x-48,0,z-48];high=[x+79,191,z+79]
    roots=[r for r in survey['trees']if isinstance(r,dict)and r.get('natural_leaves',0)>=4
           and isinstance(r.get('pos'),list)and len(r['pos'])==3
           and all(type(n)is int for n in r['pos'])
           and all(low[i]<=r['pos'][i]<=high[i]for i in range(3))]
    if not roots:raise RuntimeError('No current natural roots of the requested species')
    for box in protected:
        lo,hi=box.get('min'),box.get('max')
        if (not isinstance(lo,list)or not isinstance(hi,list)or len(lo)!=3 or len(hi)!=3
                or any(type(n)is not int for n in lo+hi)):
            raise RuntimeError('Original protected footprint is unavailable')
        if not (high[0]+16<lo[0]or low[0]-16>hi[0]or high[2]+16<lo[2]or low[2]-16>hi[2]):
            raise RuntimeError('Forest harvest would overlap a protected footprint')
    return {'item':item,'source':'natural_survey','min':low,'max':high,
            'world_session':world,'scan_id':request_id,'verified_roots':roots,
            'cache_hint_not_material_credit':True,'fixed_tree_chop':True}


def backend_client(backend, root, request):
    """Borrow only the exact existing material owner; never start a second one."""
    c = backend.ensure_client()
    if (c is not backend.client or Path(c.root).resolve() != Path(root).resolve()
            or backend.request is not request):
        raise RuntimeError('Tree trip must reuse the exact existing material backend')
    current = c.status()
    lease = current.get('supervision_lease') or {}
    if (lease.get('kind') != 'materials' or lease.get('job_session') != c.task
            or lease.get('world_session') != c.world or lease.get('revision') != c.rev):
        raise RuntimeError('Existing tree material owner is not current')
    return c


def run(root,request,candidate,species,target,out,saplings=0,return_only=False,*,backend=None):
    if species not in BIOMES or type(target)is not int or not 1<=target<=128:
        raise ValueError('Explicit supported tree species and carried target1..128 required')
    root=Path(root);out=Path(out);out.mkdir(exist_ok=False)
    if type(saplings)is not int or not 0<=saplings<=32:raise ValueError('Sapling carried target must be0..32')
    if type(return_only)is not bool:raise ValueError('Return-only must be explicit boolean')
    c = backend_client(backend,root,request) if backend is not None else None
    first=c.status() if c is not None else read_fresh(root)
    world=first['world_session'];item='minecraft:'+species+'_log'
    if (first.get('projection_selection',{}).get('key')!=request['projection_key']
            or first.get('server','').removesuffix(':25565')!=request['context']['server'].removesuffix(':25565')
            or first.get('dimension')!=request['context']['dimension']
            or first.get('health')!=20 or first.get('food',0)<18
            or first.get('manual_movement')
            or backend is None and first.get('material_task',{}).get('occupied')):
        raise RuntimeError('Original map, healthy control or native task boundary changed')
    game=root.parents[2];wanted=BIOMES[species]
    if not cache.validate_candidate(game,first['server'],first['dimension'],candidate,biome_filter=wanted):
        raise RuntimeError('Forest cache hint is no longer bound to this current world')
    if room_for_item(first,item)<target-inventory_counts(first).get(item,0):
        raise RuntimeError('Actual backpack cannot hold this wood batch')
    if not platform_input_ready(first):
        raise RuntimeError('Tree trip requires at least one plain carried dirt block for its recoverable work platform')
    profile=backend.profile if backend is not None else load(root,first)
    protected=list(profile.get('protected_regions',[]))+[first['projection_selection']]
    if c is None:
        c=MaterialClient(root,out/'control',server=first['server'],remote_finish='guard',
                         park_target=[first['pos'][0],min(315,max(160,first['pos'][1]+24)),first['pos'][2]])
    book={'schema':1,'world_session':world,'item':item,'carried_target':target,
          'candidate':route.public_candidate(candidate),'before':inventory_counts(first).get(item,0),
          'batches':[],'returned_home':False,'map_complete':False}
    ledger={};route_path=out/'resource-route.json'
    def checkpoint():
        if backend is not None:backend.checkpoint()
        s=c.status()
        if (s.get('world_session')!=world or s.get('projection_selection',{}).get('key')!=request['projection_key']
                or s.get('health',0)<19 or s.get('food',0)<18 or s.get('safety_hold',{}).get('active')):
            raise RuntimeError('Original map or healthy forest work scope changed')
        return s
    harvest_settled=True
    try:
        write_json(out/'intent.json',book);lift_for_travel(c)
        c.set_progress(phase='前往木料区')
        route.outbound(c,candidate,first['server'],first['dimension'],route_path,ledger,checkpoint,
            lambda v:cache.validate_candidate(game,first['server'],first['dimension'],v,biome_filter=wanted),
            lambda v:cache.validate_current_world(game,first['server'],first['dimension'],v))
        checkpoint();reply=c.request('scan_trees',item=item,radius=96);write_json(out/'current-trees.json',reply)
        region=current_tree_region(reply,world,c.last,item,candidate,protected)
        if saplings:region['retain_saplings']=True
        write_json(out/'current-source-region.json',region)
        profile={**profile,'resource_regions':[region]}
        route.mark_harvesting(c,route_path,json.loads(route_path.read_text()))
        for index in range(16):
            before_state=checkpoint();before=inventory_counts(before_state).get(item,0)
            seed_item=item.removesuffix('_log')+'_sapling'
            if before>=target and inventory_counts(before_state).get(seed_item,0)>=saplings:break
            c.set_progress(phase='采集木料')
            harvest_settled=False
            result=acquire(c,item,max(target,before+1),profile,out/'acquisition',checkpoint)
            after=inventory_counts(checkpoint()).get(item,0)
            stopped=checkpoint()
            harvest_settled=(result.get('phase')in('done','waiting')and after>before
                and not any(stopped.get(k)for k in('chopping','native_material_busy','navigating'))
                and stopped.get('chopper_remaining')==0 and stopped.get('chopper_platforms')==0)
            if not harvest_settled:
                from .wood_pipeline import _known_empty_chop,_unchanged_empty
                harvest_settled=_known_empty_chop(result,out/'acquisition',c,item,before_state,stopped)
                if (result.get('code')=='tree_selection_changed' and result.get('native_chop_started')is False
                        and _unchanged_empty(before_state,stopped)):
                    harvest_settled=True
            book['batches'].append({'before':before,'after':after,'receipt':result})
            write_json(out/'progress.json',book)
            print('ACTUAL_WOOD',item,after,flush=True)
            if not harvest_settled:raise RuntimeError('Wood batch lacks complete native tree/drop/cleanup proof')
            if after<=before:raise RuntimeError('Current forest has no eligible dry tree access; no harvest replay')
            if saplings:
                from drop_collection import collect_drop
                c.set_progress(phase='等待树叶自然掉落树苗');lift_for_travel(c)
                until=time.monotonic()+(120 if after>=target else 30)
                while inventory_counts(checkpoint()).get(seed_item,0)<saplings and time.monotonic()<until:
                    drop=next((e for e in checkpoint().get('entities',[]) if e.get('type')=='minecraft:item'
                        and e.get('stack',{}).get('item')==seed_item
                        and all(region['min'][i]<=e['pos'][i]<=region['max'][i]+1 for i in (0,2))),None)
                    if drop:
                        if not collect_drop(c,drop,seconds=45):raise RuntimeError('Natural sapling pickup unconfirmed; no repeated movement')
                        print('ACTUAL_SAPLINGS',inventory_counts(checkpoint()).get(seed_item,0),flush=True)
                    else:time.sleep(.5)
        book['after']=inventory_counts(checkpoint()).get(item,0)
        if book['after']<target:raise RuntimeError('Bounded forest batch ended before its carried target')
        if saplings:
            book['saplings']=inventory_counts(checkpoint()).get(seed_item,0)
            if book['saplings']<saplings:raise RuntimeError('Whole-tree batch ended before carried sapling target')
        lift_for_travel(c);route.return_home(c,checkpoint,reason='verified_wood_batch')
        book['returned_home']=True;book['return_stock']=inventory_counts(checkpoint()).get(item,0)
        if book['return_stock']<book['after']:raise RuntimeError('Wood stock changed during the confirmed return')
        write_json(out/'harvest-result.json',book)
    except Exception as error:
        book.update(state='blocked',detail=str(error),old_receipts_retained=True)
        write_json(out/'result.json',book)
        # A known read/source refusal can safely return along the existing
        # confirmed route. Unknown harvest or navigation is never followed.
        active=(json.loads(route_path.read_text()).get(route.LEDGER_KEY,{}).get('active_route')
                if route_path.exists()else None)
        if (harvest_settled and c.native_inflight is None and isinstance(active,dict)
                and active.get('state')in('candidate_arrived','harvesting','return_required')):
            lift_for_travel(c);route.return_home(c,checkpoint,reason='known_source_stop')
            book['known_stop_returned_home']=True;write_json(out/'result.json',book)
        raise
    finally:
        if (backend is None and harvest_settled and c.native_inflight is None
                and not getattr(c,'unconfirmed_native_request',None)):
            # Keep the current local protected anchor even when a source read
            # refuses before departure/return; never use a long direct home hop.
            point=local_park(c);c.checked('navigate',target=point,arrival=.25,air_only=True,seconds=90)
            s=settled_state(c,point,.55);point=[s['pos'][0],s['pos'][1]+1,s['pos'][2]]
            c.checked('material_job_park',park_target=point);c.park_target=point
        elif not harvest_settled:
            try:
                s=c.status(wait_interface=False)
                c.park_target=[s['pos'][0],min(315,s['pos'][1]+48),s['pos'][2]]
            except RuntimeError:pass
            # Existing finish still drains any uncertain native action first.
            # The fallback describes a local ascent, never an unproved home hop.
        if backend is None and c.finish() is False:raise RuntimeError('Tree trip protected finish unconfirmed')
    if backend is not None:
        book.update(phase='done',backend_owner_retained=True,construction_complete=False,
                    next_action='resume_existing_material_backend')
        write_json(out/'result.json',book);return book
    if return_only:
        book.update(construction_complete=False,map_complete=False,next_action='plant_retained_saplings_on_island')
        write_json(out/'result.json',book);return book
    result=continue_projection(root,request,out/'full-map')
    book['map_result']=result;book['construction_complete']=result.get('state')=='completed'
    book['map_complete']=False;book['final_filled_map_verification_required']=True
    write_json(out/'result.json',book);return book


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in('automation','request','candidates','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--species',choices=BIOMES,required=True);p.add_argument('--count',type=int,default=128)
    p.add_argument('--saplings',type=int,default=0)
    p.add_argument('--return-only',action='store_true')
    a=p.parse_args();rows=json.loads(a.candidates.read_text())
    if not isinstance(rows,list)or not rows:raise ValueError('No current cache candidates')
    run(a.automation,json.loads(a.request.read_text()),rows[0],a.species,a.count,a.out,a.saplings,a.return_only)

if __name__=='__main__':main()
