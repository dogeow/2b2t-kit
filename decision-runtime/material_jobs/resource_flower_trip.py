"""One cache-guided, live-verified flower harvest using one owned material client."""
import argparse
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient
from material_plan import inventory_counts
from . import bobby_snow_cache as cache,bobby_snow_route as route
from .colored_sources import acquire,_name,_point,_protected,_candidate
from .navigation import lift_for_travel
from owned_air_escape import escape_side
from .profile import load
from .projection_continuation import run as continue_projection

FLOWERS=frozenset('minecraft:'+n for n in ('white_tulip','oxeye_daisy','azure_bluet','cornflower','poppy','dandelion'))
BIOMES=frozenset('minecraft:'+n for n in ('plains','sunflower_plains','flower_forest','meadow','forest'))

def current_source(reply,world,request_id,item,low,high,profile,state):
    if (item not in FLOWERS or reply.get('id')!=request_id or reply.get('world_session')!=world
            or reply.get('phase')!='done' or reply.get('unloaded_chunks',0)
            or reply.get('scan_cells_read')!=math.prod(b-a+1 for a,b in zip(low,high))
            or reply.get('scan_total_cells')!=math.prod(b-a+1 for a,b in zip(low,high))
            or not isinstance(reply.get('blocks'),list)):
        raise RuntimeError('Flower source requires a complete current server scan')
    rows=reply['blocks'];seen=set()
    for row in rows:
        pos=row.get('pos')
        if (not _point(pos)or tuple(pos)in seen or not all(low[i]<=pos[i]<=high[i]for i in range(3))
                or any(type(row.get(k))is not bool for k in ('fluid','solid','block_entity'))):
            raise RuntimeError('Flower source rows are incomplete or ambiguous')
        seen.add(tuple(pos))
    if any(row['block_entity'] for row in rows):raise RuntimeError('Flower survey contains protected structure')
    flowers=[r for r in rows if _name(r)==item and not r['fluid']and not r['solid']
             and not _protected(r['pos'],profile,state)]
    if not flowers:raise RuntimeError('Current source has no eligible flowers')
    return {'item':item,'min':low,'max':high,'source':'natural_survey','authorized':True,
            'world_session':world,'scan_id':request_id,'observed_at':reply.get('time'),
            'verified_flower_positions':[r['pos']for r in flowers],'cached_inventory_credit':0}

def survey_bounds(candidate,low_y,source_box=None):
    x,z=candidate['tile'];low=[x,low_y,z];high=[x+15,low_y+15,z+15]
    if source_box is not None:
        a,b=source_box.get('min'),source_box.get('max')
        if(not _point(a)or not _point(b)or any(not low[i]<=a[i]<=b[i]<=high[i]for i in range(3))):
            raise ValueError('Source crop must stay inside the current candidate survey')
        low,high=a,b
    return low,high

def descent_station(reply,world,request_id,region,current_pos):
    low=[region['min'][0],min(p[1]for p in region['verified_flower_positions'])+2,region['min'][2]]
    high=[region['max'][0],319,region['max'][2]]
    volume=math.prod(b-a+1 for a,b in zip(low,high))
    if(reply.get('id')!=request_id or reply.get('world_session')!=world or reply.get('phase')!='done'
            or reply.get('unloaded_chunks',0)or reply.get('scan_cells_read')!=volume
            or reply.get('scan_total_cells')!=volume or not isinstance(reply.get('blocks'),list)):
        raise RuntimeError('Descent requires a complete current live sky-column survey')
    rows=reply['blocks'];seen=set()
    for row in rows:
        p=row.get('pos')
        if(not _point(p)or tuple(p)in seen or not all(low[i]<=p[i]<=high[i]for i in range(3))
                or any(type(row.get(k))is not bool for k in ('passable','fluid','block_entity'))):
            raise RuntimeError('Descent survey rows incomplete')
        seen.add(tuple(p))
    choices=[]
    for x,y,z in region['verified_flower_positions']:
        station=[x+.5,y+2.75,z+.5]
        if not any(r['pos'][0]==x and r['pos'][2]==z and r['pos'][1]>=math.floor(station[1])
                   and (not r['passable']or r['fluid']or r['block_entity'])for r in rows):
            choices.append(station)
    if not choices:raise RuntimeError('No actual clear column above an eligible flower; no canopy excavation')
    return min(choices,key=lambda p:(math.dist(p,current_pos),p))

def descend(c,station,checkpoint):
    here=checkpoint()['pos']
    c.checked('navigate',target=[station[0],here[1],station[2]],arrival=.15,air_only=True,seconds=60)
    for _ in range(8):
        here=checkpoint()['pos']
        if abs(here[1]-station[1])<=.55:return
        target_y=max(station[1],here[1]-48)
        c.checked('navigate',target=[here[0],target_y,here[2]],arrival=.15,air_only=True,seconds=60)
    raise RuntimeError('Bounded clear-column descent not confirmed')

def run(root,request,candidate,item,count,low_y,out,source_box=None):
    if item not in FLOWERS or type(count)is not int or not 1<=count<=64 or not -63<=low_y<=304:
        raise ValueError('Expected bounded flower target and survey level')
    low,high=survey_bounds(candidate,low_y,source_box)
    root=Path(root);out=Path(out);out.mkdir(exist_ok=False);first=read_fresh(root);world=first['world_session']
    from material_jobs_backend import require_scope
    require_scope(first,request['context'],initial=True)
    if first.get('screen') or first.get('projection_selection',{}).get('key')!=request['projection_key']:
        raise RuntimeError('Current interface or locked full map differs before flower departure')
    game=root.parents[2]
    # Candidate parsing and file hashing are completed before the heartbeat starts.
    if not cache.validate_candidate(game,first['server'],first['dimension'],candidate,biome_filter=BIOMES):
        raise RuntimeError('Current cache candidate differs')
    profile=load(root,first)
    c=MaterialClient(root,out/'control',server=first['server'],remote_finish='guard',
        park_target=[first['pos'][0],min(315,max(160,first['pos'][1]+24)),first['pos'][2]])
    book={'schema':1,'world_session':world,'item':item,'target':count,'cached_inventory_credit':0,
          'before':inventory_counts(first).get(item,0),'returned_home':False,'map_complete':False}
    path=out/'resource-route.json';ledger={};settled=True
    def checkpoint():
        s=c.status()
        if(s['world_session']!=world or s['health']<19 or s['food']<18
                or s.get('projection_selection',{}).get('key')!=request['projection_key']):
            raise RuntimeError('Original map or healthy flower work scope changed')
        return s
    try:
        c.start_progress('采集染料原料',count,phase='前往已缓存花源')
        lift_for_travel(c)
        route.outbound(c,candidate,first['server'],first['dimension'],path,ledger,checkpoint,
            lambda v:cache.validate_candidate(game,first['server'],first['dimension'],v,biome_filter=BIOMES),
            lambda v:cache.validate_current_world(game,first['server'],first['dimension'],v))
        r=c.request('scan',min=low,max=high,details=True);write_json(out/'live-source-scan.json',r)
        region=current_source(r,world,c.last,item,low,high,profile,checkpoint())
        write_json(out/'live-source-region.json',region)
        profile={**profile,'colored_source_regions':[region]}
        route.mark_harvesting(c,path,json.loads(path.read_text()))
        sky_low=[low[0],min(p[1]for p in region['verified_flower_positions'])+2,low[2]]
        sky_high=[high[0],319,high[2]]
        sky=c.request('scan',min=sky_low,max=sky_high,details=True);write_json(out/'live-descent-columns.json',sky)
        station=descent_station(sky,world,c.last,region,checkpoint()['pos'])
        write_json(out/'descent-station.json',{'station':station,'native_collision_checks_retained':True})
        descend(c,station,checkpoint)
        for index in range(32):
            before=inventory_counts(checkpoint()).get(item,0)
            if before>=count:break
            settled=False
            receipt=acquire(c,item,count,profile,out/'acquisition',checkpoint)
            after=inventory_counts(checkpoint()).get(item,0)
            settled=(receipt.get('phase')in ('done','waiting')and receipt.get('code')!='WAIT_RECONCILE'
                     and c.native_inflight is None and not getattr(c,'unconfirmed_native_request',None))
            book.setdefault('batches',[]).append({'before':before,'after':after,'receipt':receipt})
            write_json(out/'progress.json',book);c.set_progress(done=after)
            if not settled or after<=before:raise RuntimeError('Flower batch unconfirmed or has no actual gain')
        book['harvested']=inventory_counts(checkpoint()).get(item,0)
        if book['harvested']<count:raise RuntimeError('Flower target not reached')
        escape_side(c,out/'return-ascent',target_y=160,pickup_items=(item,))
        route.return_home(c,checkpoint,reason='verified_flower_batch')
        book['returned_home']=True;book['return_stock']=inventory_counts(checkpoint()).get(item,0)
        if book['return_stock']<book['harvested']:raise RuntimeError('Flower stock changed during return')
        write_json(out/'harvest-result.json',book)
    except Exception as error:
        book.update(state='blocked',detail=str(error),old_receipts_retained=True)
        write_json(out/'result.json',book);raise
    finally:
        if settled and c.native_inflight is None and not getattr(c,'unconfirmed_native_request',None):c.finish()
        else:write_json(out/'unknown-action-retained.json',{'no_resource_or_return_replay':True,'world_session':world})
    result=continue_projection(root,request,out/'full-map')
    book['map_result']=result;book['map_complete']=False;book['final_filled_map_verification_required']=True
    write_json(out/'result.json',book);return book

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('automation','request','candidates','out'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--item',choices=sorted(FLOWERS),required=True);p.add_argument('--count',type=int,default=17)
    p.add_argument('--low-y',type=int,default=62)
    p.add_argument('--source-box',type=Path)
    a=p.parse_args();rows=json.loads(a.candidates.read_text())
    if not isinstance(rows,list)or not rows:raise ValueError('No current candidate')
    box=json.loads(a.source_box.read_text())if a.source_box else None
    run(a.automation,json.loads(a.request.read_text()),rows[0],a.item,a.count,a.low_y,a.out,box)

if __name__=='__main__':main()
