"""Ordinary armor-stand item placement at exact translated original entity positions."""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_wood import cell_at
from material_jobs.local_air_path import move


def placement_pose(expected):
    yaw=expected['yaw']%360;x,y,z=expected['pos']
    # Vanilla snaps player yaw minus 180 to 45 degrees. Place from the
    # corresponding side so the ordinary block-use aim itself gives that yaw.
    if yaw not in(0,90,180,270):raise ValueError('Only original cardinal stand rotations supported')
    dx,dz={0:(0,2),90:(-2,0),180:(0,-2),270:(2,0)}[yaw]
    return [x+dx,y+.1,z+dz]


def matches(expected,actual):
    return (actual.get('type')=='minecraft:armor_stand'
        and math.dist(actual.get('pos',[math.inf]*3),expected['pos'])<=.15
        and abs((actual.get('yaw',math.inf)-expected['yaw']+180)%360-180)<2
        and all(actual.get(k)==expected[k]for k in ('small','show_arms','base_plate','default_pose','invisible')))


def place(c,expected,out,checkpoint):
    if (expected.get('type')!='minecraft:armor_stand'or expected.get('small')
            or expected.get('show_arms')or not expected.get('base_plate')
            or not expected.get('default_pose')or expected.get('invisible')):
        raise ValueError('Original ordinary empty armor stand required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);q=checkpoint();key=q['projection_selection']['key'];p=expected['pos'];support=[math.floor(p[0]),round(p[1])-1,math.floor(p[2])]
    if p[1]!=round(p[1])or not all(a<=v<=b+1 for a,v,b in zip(q['projection_selection']['min'],p,q['projection_selection']['max'])):raise RuntimeError('Original entity outside placement')
    anchor=cell_at(c,support)
    if not anchor.get('solid')or anchor.get('fluid')or anchor.get('block_entity'):raise RuntimeError('Dry ordinary original floor required')
    move(c,placement_pose(expected),out/'original-placement-pose',foot_offset=.1,max_horizontal=24,exact_target=True)
    observations=[];ids=set()
    for _ in range(2):
        checkpoint();a=c.request('projection_audit')['projection_audit']
        if a['placement_key']!=key or not a.get('loaded_chunks_verified'):raise RuntimeError('Original decoration scope changed')
        near=[e for e in a.get('decorations',[])if e['type']=='minecraft:armor_stand'and math.dist(e['pos'],p)<.25]
        if near:
            if len(near)==1 and matches(expected,near[0]):return {'already_matched':True,'new_entity':False,'actual':near[0]}
            raise RuntimeError('Original stand location is occupied; no new entity placed')
        ids.update(e['uuid']for e in a.get('decorations',[]));observations.append(a['observed_at']);time.sleep(.15)
    before=inventory_counts(c.status())['minecraft:armor_stand']
    if before<1:raise RuntimeError('Actual carried stand required')
    c.checked('select_item',item='minecraft:armor_stand');book={'world_session':c.world,'placement_key':key,'expected':expected,'support':anchor,'inventory_before':before,'existing_entity_ids':sorted(ids),'pending':'one_ordinary_armor_stand_use','complete':False};path=out/'armor-stand.json';write_json(path,book)
    try:r=c.checked('interact',pos=support,face='up',expected_state=anchor['state'],expected_hand='minecraft:armor_stand')
    finally:book['request_id']=c.last;write_json(path,book)
    write_json(out/'native-ordinary-use.json',r);end=time.monotonic()+6;stamps=[];actual=None
    while True:
        checkpoint();a=c.request('projection_audit')['projection_audit'];now=inventory_counts(c.status())['minecraft:armor_stand'];new=[e for e in a.get('decorations',[])if e['type']=='minecraft:armor_stand'and e['uuid']not in ids and math.dist(e['pos'],p)<.25]
        if len(new)==1 and matches(expected,new[0])and now==before-1:
            actual=new[0]
            if a['observed_at']not in stamps:stamps.append(a['observed_at'])
        else:stamps=[]
        if len(stamps)>=2:break
        if time.monotonic()>end:raise RuntimeError('Original armor stand appearance or stock not confirmed; no duplicate use')
        time.sleep(.1)
    book.update(complete=True,pending=None,actual=actual,inventory_after=before-1,entity_observation_times=stamps);write_json(path,book);print('ORIGINAL_ARMOR_STAND_MATCHED',p,actual['yaw'],flush=True);return book
