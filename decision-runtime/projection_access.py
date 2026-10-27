"""Open an observed trapdoor directly above the selected design's ladder shaft."""
import json,math,time
from projection_completion import block_state
from kit_runtime.journal import write_json


def _observe_hatch(client,pos,expected):
    deadline=time.monotonic()+4;first=None
    while time.monotonic()<deadline:
        reply=client.request('scan',min=pos,max=pos,details=True)
        rows=reply.get('blocks')
        if (reply.get('phase') not in (None,'done') or not isinstance(rows,list)
                or len(rows)!=1 or rows[0].get('pos')!=pos):
            raise RuntimeError('Current ladder hatch observation is incomplete')
        stamp=client.status().get('time')
        if rows[0].get('state')==expected:
            if first is not None and type(stamp)is int and stamp-first>=400:return rows[0]
            if first is None and type(stamp)is int:first=stamp
        else:first=None
        time.sleep(.1)
    raise RuntimeError('Hatch interaction unconfirmed; retain intent without replay')


def _toggle(client,row,book,path,wanted):
    from door_access import crossing_hand
    from work_access import approach_faces
    if book.get('pending'):raise RuntimeError('Original hatch interaction unresolved; never replay')
    current=client.status()
    if current.get('projection_selection',{}).get('key')!=book['placement_key']:
        raise RuntimeError('Projection changed before hatch interaction')
    if math.dist(current['pos'],[v+.5 for v in row['pos']])>3:
        approach_faces(client,row['pos'],row['state'],['up','down','north','south','west','east'],seconds=30)
    hand=crossing_hand(client.status());client.checked('select_item',item=hand)
    face='down'if client.status()['pos'][1]<row['pos'][1]else'up'
    book['pending']={'pos':row['pos'],'before':row['state'],'expected':wanted};write_json(path,book)
    try:client.checked('interact',pos=row['pos'],face=face,expected_state=row['state'],expected_hand=hand)
    finally:
        book['pending']['request_id']=getattr(client,'last',None);write_json(path,book)
    actual=_observe_hatch(client,row['pos'],wanted)
    book['pending']=None;book['after']=actual;write_json(path,book);return actual


def _open_model_hatch(client,column,model):
    state=client.status();key=state.get('projection_selection',{}).get('key')
    if (model.get('placement_key')!=key or not model.get('content_hash')
            or model.get('loaded_chunks_verified')is not True or not isinstance(model.get('expected'),list)):
        raise RuntimeError('Full current projection model required for a completed ladder')
    path=client.out/'basement-hatch.json'
    if path.exists():raise RuntimeError('Original hatch journal retained; never replay opening')
    ladders=[r for r in model['expected']if r['pos'][::2]==column and block_state(r['state'])[0]=='minecraft:ladder']
    if not ladders:return None
    bottom=min(r['pos'][1]for r in ladders);top=max(r['pos'][1]for r in ladders)
    if top-bottom>16 or {r['pos'][1]for r in ladders}!=set(range(bottom,top+1)):
        raise RuntimeError('Only a continuous bounded existing ladder shaft is supported')
    pos=[column[0],top+1,column[1]]
    expected=next((r for r in model['expected']if r['pos']==pos),None)
    if expected is None or not block_state(expected['state'])[0].endswith('_trapdoor'):
        raise RuntimeError('Model does not identify the existing ladder hatch')
    reply=client.request('scan',min=[column[0],bottom,column[1]],max=pos,details=True)
    if reply.get('phase')not in(None,'done')or not isinstance(reply.get('blocks'),list):
        raise RuntimeError('Existing ladder shaft scan is incomplete')
    rows={tuple(r['pos']):r for r in reply['blocks']}
    if any(rows.get(tuple(r['pos']),{}).get('state')!=r['state']for r in ladders):
        raise RuntimeError('Actual ladder changed; no hatch interaction')
    row=rows.get(tuple(pos));name,props=block_state(row['state']if row else'')
    target_name,target_props=block_state(expected['state'])
    if (name!=target_name or row.get('fluid')is not False or props.get('powered')!='false'
            or props.get('open')not in('true','false')
            or {k:v for k,v in props.items()if k!='open'}!={k:v for k,v in target_props.items()if k!='open'}):
        raise RuntimeError('Original ladder hatch identity changed')
    book={'placement_key':key,'world_session':state.get('world_session'),'model_hash':model['content_hash'],
          'before':row,'after':row,'pending':None,'restored':props['open']=='true',
          'confirmation_scope':'repeated_loaded_world_observation_not_packet_ack'}
    write_json(path,book)
    if props['open']=='true':return row
    wanted=row['state'].replace('open=false','open=true')
    return _toggle(client,row,book,path,wanted)


def open_ladder_hatch(client, column, *, model=None):
    if model is not None:return _open_model_hatch(client,column,model)
    state=client.status()
    audit=client.request('projection_audit')['projection_audit']
    if audit['placement_key']!=state['projection_selection']['key']:
        raise RuntimeError('Projection changed before opening basement access')
    saved_path=client.out/'basement-hatch.json'
    saved=json.loads(saved_path.read_text()) if saved_path.exists() else {}
    known=saved.get('after',{})
    cached=saved.get('placement_key')==audit['placement_key'] and len(known.get('pos',[]))==3 and [known['pos'][0],known['pos'][2]]==column
    ladders=[r for r in audit['mismatches'] if r['pos'][0]==column[0] and r['pos'][2]==column[1]
             and block_state(r['expected'])[0]=='minecraft:ladder']
    if not ladders and not cached:return None
    if cached:low=high=known['pos']
    else:
        top=max(r['pos'][1] for r in ladders)
        low=[column[0],top+1,column[1]];high=[column[0],top+2,column[1]]
    rows=client.request('scan',min=low,max=high,details=True)['blocks']
    hatches=[r for r in rows if block_state(r['state'])[0].endswith('_trapdoor') and not r['fluid']]
    if len(hatches)!=1:raise RuntimeError('Expected ladder hatch was not uniquely observed')
    row=hatches[0];_,properties=block_state(row['state'])
    if properties.get('open')=='true':
        saved_path.write_text(json.dumps({'placement_key':audit['placement_key'],'before':row,'after':row}))
        return row
    if properties.get('open')!='false':raise RuntimeError('Unknown hatch state')
    face='down' if client.status()['pos'][1]<row['pos'][1] else 'up'
    client.checked('approach_block',pos=row['pos'],face=face,expected_state=row['state'],seconds=120)
    client.checked('select_item',item='minecraft:diamond_sword')
    client.checked('interact',pos=row['pos'],face=face,expected_state=row['state'],expected_hand='minecraft:diamond_sword')
    observed=client.request('scan',min=row['pos'],max=row['pos'],details=True)['blocks']
    if len(observed)!=1 or block_state(observed[0]['state'])[1].get('open')!='true':
        raise RuntimeError('Hatch opening was not confirmed; do not toggle it again')
    saved_path.write_text(json.dumps({'placement_key':audit['placement_key'],'before':row,'after':observed[0]},ensure_ascii=False,indent=2))
    print('HATCH_OPEN',row['pos'],flush=True)
    return observed[0]


def restore_ladder_hatch(client):
    path=client.out/'basement-hatch.json'
    if not path.exists():return
    book=json.loads(path.read_text())
    if book.get('pending'):raise RuntimeError('Original hatch interaction unresolved; no cleanup replay')
    if book.get('restored'):return
    state=client.status()
    if (state.get('projection_selection',{}).get('key')!=book.get('placement_key')
            or state.get('world_session')!=book.get('world_session')):
        raise RuntimeError('Hatch ownership changed; preserve player state')
    before,after=book['before'],book['after'];reply=client.request('scan',min=after['pos'],max=after['pos'],details=True)
    rows=reply.get('blocks')or[]
    if len(rows)!=1 or rows[0].get('pos')!=after['pos']or rows[0].get('state')!=after['state']:
        raise RuntimeError('Hatch changed after opening; preserve the new state')
    _toggle(client,rows[0],book,path,before['state'])
    book['restored']=True;write_json(path,book)


def ladder_room_route(rows,start,shaft,low,high):
    """Reach an air cell beside a real ladder, routing around new furniture."""
    from material_jobs.local_air_path import plan
    from material_jobs.protocol import JobBlocked
    paths=[]
    for dx,dz in((1,0),(0,1),(-1,0),(0,-1)):
        target=[shaft[0]+dx+.5,shaft[1]+.2,shaft[2]+dz+.5]
        try:points=plan(rows,start,target,low,high,foot_offset=.2,max_straight=8)
        except JobBlocked:continue
        paths.append(points)
    if not paths:raise JobBlocked('Existing ladder has no connected observed air approach; preserve the room')
    return min(paths,key=lambda p:sum(math.dist(a,b)for a,b in zip([start]+p,p)))


def ladder_descent_geometry(model, rows, column):
    """Identify a complete original dry shaft without treating its plates as air."""
    ladders=[r for r in model.get('expected',[])if r.get('pos',[])[::2]==column
             and block_state(r.get('state',''))[0]=='minecraft:ladder']
    if not ladders:raise RuntimeError('No original ladder column in this model')
    bottom=min(r['pos'][1]for r in ladders);top=max(r['pos'][1]for r in ladders)
    if top-bottom>16 or {r['pos'][1]for r in ladders}!=set(range(bottom,top+1)):
        raise RuntimeError('Only a continuous bounded original ladder is supported')
    facing={block_state(r['state'])[1].get('facing')for r in ladders}
    cells={tuple(r['pos']):r for r in rows}
    if len(facing)!=1 or not facing<={'east','west','south','north'}:
        raise RuntimeError('Original ladder facing is inconsistent')
    for row in ladders:
        actual=cells.get(tuple(row['pos']),{})
        if (actual.get('state')!=row['state']or actual.get('fluid')is not False
                or actual.get('block_entity')is not False
                or block_state(row['state'])[1].get('waterlogged')!='false'):
            raise RuntimeError('Existing dry ladder changed before descent')
    for y in (top+1,top+2):
        row=cells.get((column[0],y,column[1]))
        if row:
            name,props=block_state(row['state'])
            if (y!=top+1 or not name.endswith('_trapdoor')or props.get('open')!='true'
                    or props.get('powered')!='false'or row.get('fluid')is not False):
                raise RuntimeError('Existing ladder top is obstructed or its hatch is closed')
    return {'bottom':bottom,'top':top,'facing':next(iter(facing))}


def descend_existing_ladder(client,model,column,out):
    """Descend through real ladder shapes using unchanged native collision admission."""
    from pathlib import Path
    from material_jobs.navigation import _air_scan,settled_state
    from material_jobs.local_air_path import move
    state=client.status();key=state.get('projection_selection',{}).get('key')
    if (model.get('placement_key')!=key or not model.get('content_hash')
            or model.get('loaded_chunks_verified')is not True):
        raise RuntimeError('Current complete model required for ladder descent')
    low=[v-2 for v in model['bounds']['min']];high=[v+2 for v in model['bounds']['max']]
    rows=_air_scan(client,low,high);g=ladder_descent_geometry(model,rows,column)
    route=ladder_room_route(rows,client.status()['pos'],[column[0],g['top']+1,column[1]],low,high)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    book={'world_session':state['world_session'],'placement_key':key,'model_hash':model['content_hash'],
          'geometry':g,'approach':route,'pending':None,'complete':False,'mining_sent':False,
          'ladder_blocks_preserved':True,'real_shape_gate_required':True}
    write_json(out/'route.json',book)
    for i,point in enumerate(route[1:]):
        move(client,point,out/('approach-%02d'%i),foot_offset=.2,max_horizontal=24)
    dx,dz={'east':(.1,0),'west':(-.1,0),'south':(0,.1),'north':(0,-.1)}[g['facing']]
    x,z=column[0]+.5+dx,column[1]+.5+dz
    for point in ([x,g['top']+1.2,z],[x,g['bottom']+.2,z]):
        # Never remove ladder cells from a scan or call them empty. Admission
        # and every movement tick independently check their real collision.
        fresh=_air_scan(client,[column[0],g['bottom'],column[1]],[column[0],g['top']+2,column[1]])
        ladder_descent_geometry(model,fresh,column)
        book['pending']={'target':point};write_json(out/'route.json',book)
        try:client.checked('navigate',target=point,arrival=.2,air_only=True,seconds=30)
        finally:
            book['pending']['request_id']=client.last;write_json(out/'route.json',book)
        settled_state(client,point,.5);book['pending']=None;write_json(out/'route.json',book)
    book.update(complete=True,actual=client.status()['pos']);write_json(out/'route.json',book);return book


def leave_ladder_room(client,model,column,out):
    from pathlib import Path
    from material_jobs.navigation import _air_scan,settled_state
    from material_jobs.local_air_path import move
    state=client.status();key=state.get('projection_selection',{}).get('key')
    if key!=model.get('placement_key')or not model.get('content_hash'):
        raise RuntimeError('Current complete model required for ladder room exit')
    ladders=[r for r in model['expected']if r['pos'][::2]==column and block_state(r['state'])[0]=='minecraft:ladder']
    if not ladders:raise RuntimeError('No original ladder column in this model')
    bottom=min(r['pos'][1]for r in ladders);top=max(r['pos'][1]for r in ladders)
    if top-bottom>16:raise RuntimeError('Ladder room exit exceeds bounded height')
    low=[v-2 for v in model['bounds']['min']];high=[v+2 for v in model['bounds']['max']]
    rows=_air_scan(client,low,high);cells={tuple(r['pos']):r for r in rows}
    if any(cells.get(tuple(r['pos']),{}).get('state')!=r['state']for r in ladders):
        raise RuntimeError('Existing ladder changed before exit')
    hatch=cells.get((column[0],top+1,column[1]));name,props=block_state(hatch['state']if hatch else'')
    if not name.endswith('_trapdoor')or props.get('open')!='true'or hatch.get('fluid')is not False:
        raise RuntimeError('Existing ladder hatch is no longer open and dry')
    path=ladder_room_route(rows,client.status()['pos'],[column[0],bottom,column[1]],low,high)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    book={'world_session':state.get('world_session'),'placement_key':key,'model_hash':model['content_hash'],
          'route':path,'pending':None,'complete':False,'mining_sent':False,'real_shape_gate_required':True}
    write_json(out/'route.json',book)
    for index,point in enumerate(path[1:]):
        move(client,point,out/('air-%02d'%index),foot_offset=.2,max_horizontal=24)
    facing=block_state(ladders[0]['state'])[1].get('facing')
    dx,dz={'east':(.1,0),'west':(-.1,0),'south':(0,.1),'north':(0,-.1)}.get(facing,(0,0))
    # Leave a small real-shape margin from the thin ladder plate; native
    # collision admission still checks both the ladder and the open hatch.
    shaft_x,shaft_z=column[0]+.5+dx,column[1]+.5+dz
    for point in([shaft_x,bottom+.2,shaft_z],[shaft_x,top+2.2,shaft_z]):
        # These occupied ladder/hatch cells remain real blocks. The unchanged
        # native gate checks their actual shapes before and during movement.
        book['pending']={'target':point};write_json(out/'route.json',book)
        try:client.checked('navigate',target=point,arrival=.2,air_only=True,seconds=45)
        finally:
            book['pending']['request_id']=getattr(client,'last',None);write_json(out/'route.json',book)
        settled_state(client,point,.5);book['pending']=None;write_json(out/'route.json',book)
    book.update(complete=True,actual=client.status()['pos']);write_json(out/'route.json',book);return book
