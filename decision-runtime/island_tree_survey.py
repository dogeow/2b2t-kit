"""Read current island tree species through one existing guarded Kit client.

Bounds describe the surveyed area only. This command never mines, plants,
changes supply permissions or credits materials from a tree observation.
"""
import argparse
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient
from material_jobs.acquisition import _travel
from material_jobs.navigation import lift_for_travel, local_park, settled_state


def centers(low, high, radius=96):
    if (not isinstance(low, list) or not isinstance(high, list) or len(low)!=2 or len(high)!=2
            or any(type(n)is not int for n in low+high)
            or type(radius)is not int or not 8<=radius<=96
            or any(a>b or b-a>512 or max(abs(a),abs(b))>29_999_800 for a,b in zip(low,high))):
        raise ValueError('Survey requires bounded integer XZ and radius8..96')
    axes=[]
    for a,b in zip(low,high):
        if b-a<=2*radius:
            axes.append([(a+b)//2])
        else:
            start,end=a+radius,b-radius
            count=math.ceil((end-start)/(2*radius))+1
            axes.append([round(start+(end-start)*i/(count-1))for i in range(count)])
    return [[x,z]for x in axes[0]for z in axes[1]]


def safe(client, first):
    s=client.status()
    if (s.get('world_session')!=first['world_session'] or s.get('health')!=20 or s.get('food',0)<18
            or s.get('projection_selection',{}).get('key')!=first.get('projection_selection',{}).get('key')
            or s.get('manual_movement') or s.get('under_water') or s.get('screen')
            or not s.get('guard_armed') or not s.get('guard_pve_only')
            or s.get('safety_hold',{}).get('active')):
        raise RuntimeError('Current world, selected map, health or player control changed')
    return s


def current_survey(reply, world, request_id, center):
    survey=reply.get('tree_survey')or{}
    point=reply.get('pos')
    # This existing native read protocol omits action phase; its exact request,
    # world, actual center and complete column counts identify the observation.
    if (reply.get('phase') not in (None,'done') or reply.get('world_session')!=world
            or reply.get('id')!=request_id
            or not isinstance(point,list)or len(point)!=3
            or any(type(n)not in(int,float)or not math.isfinite(n)for n in point)
            or [math.floor(point[0]),math.floor(point[2])]!=center
            or type(survey.get('loaded_columns'))is not int or survey['loaded_columns']!=193*193
            or type(survey.get('unloaded_columns'))is not int or survey['unloaded_columns']!=0
            or not isinstance(survey.get('trees'),list)):
        raise RuntimeError('Island tree coverage is incomplete; no absence conclusion')
    return survey


def run(root, low, high, species, out):
    points=centers(low,high)
    species=list(dict.fromkeys(species))
    if not species or any(n not in ('dark_oak','spruce','oak','birch','cherry','acacia')for n in species):
        raise ValueError('Explicit supported tree species required')
    out=Path(out);out.mkdir(exist_ok=False)
    first=read_fresh(root)
    if first.get('material_task',{}).get('occupied'):
        raise RuntimeError('Existing material task still owns the player')
    write_json(out/'intent.json',{'world_session':first['world_session'],'area_min_xz':low,
        'area_max_xz':high,'radius':96,'centers':points,'species':species,
        'read_only_material_survey':True,'material_credit':0})
    c=MaterialClient(root,out/'control',server=first['server'],remote_finish='guard',
                     park_target=[first['pos'][0],max(100,first['pos'][1]),first['pos'][2]])
    book={'schema':1,'world_session':c.world,'area_min_xz':low,'area_max_xz':high,
          'observations':[],'roots':{n:[]for n in species},'complete':False,'material_credit':0}
    try:
        safe(c,first);lift_for_travel(c)
        for index,(x,z) in enumerate(points):
            s=safe(c,first)
            target=[x+.5,max(100,s['pos'][1]),z+.5]
            if math.hypot(target[0]-c.anchor[0],target[2]-c.anchor[2])>480:
                raise RuntimeError('Island observation would leave this owned local worksite')
            trace=[];_travel(c,target,lambda:safe(c,first),trace,keep_cruise=True)
            write_json(out/('travel-%02d.json'%index),trace)
            for name in species:
                safe(c,first)
                reply=c.request('scan_trees',item='minecraft:'+name+'_log',radius=96)
                write_json(out/('survey-%02d-%s.json'%(index,name)),reply)
                survey=current_survey(reply,c.world,c.last,[x,z])
                entry={'center_index':index,'species':name,'request_id':reply['id'],
                       'loaded_columns':survey['loaded_columns'],'roots_seen':len(survey['trees']),
                       'biomes':survey.get('biomes')}
                book['observations'].append(entry)
                for tree in survey['trees']:
                    pos=tree.get('pos')
                    if (not isinstance(pos,list)or len(pos)!=3 or any(type(n)is not int for n in pos)):
                        raise RuntimeError('Invalid current tree root')
                    if (low[0]<=pos[0]<=high[0] and low[1]<=pos[2]<=high[1]
                            and pos not in [r['pos']for r in book['roots'][name]]):
                        book['roots'][name].append(tree)
                write_json(out/'progress.json',book)
                print(json.dumps(entry,ensure_ascii=False),flush=True)
        book['complete']=True
        write_json(out/'result.json',book)
        return book
    finally:
        # Unknown native requests stay with MaterialClient's existing finish
        # lifecycle; never issue another navigation while one is unresolved.
        if c.native_inflight is None and not getattr(c,'unconfirmed_native_request',None):
            s=safe(c,first);point=local_park(c)
            c.checked('navigate',target=point,arrival=.25,air_only=True,seconds=90)
            s=settled_state(c,point,.55);point=[s['pos'][0],s['pos'][1]+1,s['pos'][2]]
            c.checked('material_job_park',park_target=point);c.park_target=point
        if c.finish() is False:
            raise RuntimeError('Island survey protected finish not confirmed')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--automation',type=Path,required=True)
    p.add_argument('--min-xz',type=int,nargs=2,required=True)
    p.add_argument('--max-xz',type=int,nargs=2,required=True)
    p.add_argument('--species',nargs='+',required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.automation,a.min_xz,a.max_xz,a.species,a.out)

if __name__=='__main__':main()
