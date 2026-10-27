"""Return from below a selected roof through existing air only; never excavate."""
from pathlib import Path
import math,time
from kit_runtime.journal import write_json
from material_jobs.local_air_path import move
from material_jobs.protocol import JobBlocked
from roof_slab_window_plan import SLAB
from roof_double_slab_plan import DOUBLE


def prepare(builder,model,out,*,y=72):
    out=Path(out);out.mkdir(exist_ok=False);file=out/'progress.json';book={'ready':False,'mining_sent':False,'block_placement_sent':False,'attempts':[]};write_json(file,book)
    deadline=time.monotonic()+30
    while True:
        a=builder.client.status();assert a.get('health',0)>=19 and not a.get('manual_movement')and not a.get('screen')
        if a['health']==20 and not a.get('guard_busy'):break
        if time.monotonic()>deadline:raise RuntimeError('Native defense or health recovery still active; no roof access sent')
        time.sleep(.2)
    initial=builder.check();start=initial['pos'];book.update(world_session=initial['world_session'],start=start)
    if start[1]>=y+1:
        book.update(ready=True,reason='already_above_roof_work_plane');write_json(file,book);return book
    roof=[v['pos']for v in model['expected']if v['pos'][1]==y and v['state']in (SLAB,DOUBLE)]
    if not roof:raise RuntimeError('Pinned roof layer absent')
    xs=[p[0]for p in roof];zs=[p[2]for p in roof];tx=min(max(start[0],min(xs)+.5),max(xs)+.5);tz=min(max(start[2],min(zs)+.5),max(zs)+.5)
    targets=[[min(xs)-.5,y+8.1,tz],[max(xs)+1.5,y+8.1,tz],[tx,y+8.1,min(zs)-.5],[tx,y+8.1,max(zs)+1.5]]
    targets=sorted((v for v in targets if math.hypot(v[0]-start[0],v[2]-start[2])<=24 and abs(v[1]-start[1])<=64),key=lambda v:math.dist(start,v))
    builder.n('select_item',item='minecraft:netherite_sword')
    for index,target in enumerate(targets):
        builder.check();folder=out/f'edge-{index:02d}';low=[math.floor(min(start[0],target[0]))-3,math.floor(start[1]),math.floor(min(start[2],target[2]))-3];high=[math.floor(max(start[0],target[0]))+3,math.ceil(max(start[1],target[1]))+3,math.floor(max(start[2],target[2]))+3];attempt={'target':target,'scan_bounds':{'min':low,'max':high}};book['attempts'].append(attempt);write_json(file,book)
        try:
            move(builder.client,target,folder,max_straight=12,foot_offset=.1,max_horizontal=24,exact_target=True,scan_bounds={'min':low,'max':high})
            actual=builder.check()
            if math.dist(actual['pos'],target)>.6:raise RuntimeError('Actual roof access endpoint not confirmed')
            attempt['complete']=True;book.update(ready=True,end=actual['pos']);write_json(file,book);return book
        except JobBlocked as error:
            attempt['blocked']=repr(error);write_json(file,book)
            if getattr(builder.client,'unconfirmed_native_request',None)is not None:raise
            if(folder/'local-air-path.json').exists():
                book['reason']='observed_route_changed_after_path_was_planned';write_json(file,book);return book
            if math.dist(builder.check()['pos'],start)>.12:
                book['reason']='owned_position_changed_during_access_preflight';write_json(file,book);return book
    book['reason']='no_existing_bounded_air_route_to_roof_edge';write_json(file,book);return book
