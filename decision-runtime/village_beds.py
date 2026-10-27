"""One normal directional bed placement, with both real halves and stock conservation."""
from pathlib import Path
import json,hashlib,math,time
from material_plan import inventory_counts
from kit_runtime.journal import write_json

DELTAS={'north':[0,0,-1],'south':[0,0,1],'east':[1,0,0],'west':[-1,0,0]}
def empty_bed_body(rows,foot,head,stand):
    """Bed halves stay empty; harmless attachments may share player space."""
    def attachment(cell):
        row=rows.get(tuple(cell))
        if row is None:return True
        name=row.get('state','').split('}',1)[0].removeprefix('Block{')
        return (row.get('passable') is True and row.get('fluid') is False
                and row.get('block_entity') is False
                and (name in ('minecraft:lever','minecraft:torch','minecraft:wall_torch')
                     or name.startswith('minecraft:') and name.endswith('_button')))
    return (tuple(foot)not in rows and tuple(head)not in rows
            and attachment(stand)
            and all(attachment([cell[0],cell[1]+1,cell[2]])for cell in(foot,head,stand)))

def cells(foot,facing):
    if facing not in DELTAS or not isinstance(foot,list)or len(foot)!=3 or any(type(v)is not int for v in foot):raise ValueError('Integer bed foot and horizontal facing required')
    d=DELTAS[facing];head=[foot[i]+d[i]for i in range(3)];stand=[foot[i]-d[i]for i in range(3)]
    return head,stand

def founder_layout(origin,boat_cell):
    """Six beds in a 9x9 enclosure, keeping the actual boat's 5x5 landing clear."""
    if(any(not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)for p in(origin,boat_cell))
            or boat_cell[1]!=origin[1]or boat_cell[2]-origin[2]!=4 or boat_cell[0]-origin[0]not in(3,4,5)):
        raise ValueError('Exact 9x9 founder enclosure origin and interior boat floor required')
    bx=boat_cell[0]-origin[0];local=[]
    sides=(7,)if bx==3 else(1,)if bx==5 else(1,7)
    for x in sides:local.extend(((x,3,'north'),(x,5,'south')))
    for z in(1,7):
        local.extend(((4,z,'west'),)if bx==4 else((3,z,'west'),(5,z,'east')))
    result=[]
    for x,z,facing in local:
        foot=[origin[0]+x,origin[1],origin[2]+z];head,stand=cells(foot,facing)
        result.append({'foot':foot,'head':head,'stand':stand,'facing':facing})
    return result
def matches(row,item,part,facing):
    text=(row or{}).get('state','')
    return text.startswith('Block{'+item+'}')and 'part='+part in text and'facing='+facing in text

def place(c,foot,facing,out,checkpoint,item='minecraft:white_bed'):
    head,stand=cells(foot,facing)
    if item!='minecraft:white_bed':raise ValueError('This village plan currently uses white beds')
    low=[min(foot[i],head[i],stand[i])-1 for i in range(3)];high=[max(foot[i],head[i],stand[i])+1 for i in range(3)];low[1]=foot[1]-1;high[1]=foot[1]+2
    def survey():
        checkpoint();r=c.checked('scan',min=low,max=high,details=True)
        if r.get('scan_cells_read')!=r.get('scan_total_cells')or r.get('unloaded_chunks',0):raise RuntimeError('Complete current bed scene is required')
        return r,{tuple(v['pos']):v for v in r['blocks']}
    q,rows=survey()
    if matches(rows.get(tuple(foot)),item,'foot',facing)and matches(rows.get(tuple(head)),item,'head',facing):
        return {'complete':True,'placed':False,'existing_bed_verified':True,'foot':foot,'head':head,'inventory_credit':0}
    if not empty_bed_body(rows,foot,head,stand):
        raise RuntimeError('Bed halves and standing cell need empty body space over dry solid floors')
    for cell in (foot,head,stand):
        floor=rows.get((cell[0],cell[1]-1,cell[2]),{})
        if not floor.get('solid')or floor.get('fluid')or floor.get('block_entity'):
            raise RuntimeError('Bed halves and standing cell need empty body space over dry solid floors')
    for e in q.get('scan_entities',[]):
        bounds=e.get('bounds')or{}
        if not bounds:raise RuntimeError('Observed entity bounds unavailable')
        for cell in (foot,head):
            if all(bounds['max'][i]>cell[i]and bounds['min'][i]<cell[i]+1 for i in range(3)):
                raise RuntimeError('An entity intersects the new bed; no placement')
    if inventory_counts(q)[item]<1:raise RuntimeError('No carried white bed')
    floor=[stand[0],stand[1]-1,stand[2]];source=rows[tuple(floor)]
    c.checked('approach_block',pos=floor,face='up',expected_state=source['state'],stand_distance=.35,seconds=60)
    c.checked('select_item',item=item);q,rows=survey()
    if math.dist(q['pos'],[stand[0]+.5,stand[1]+.02,stand[2]+.5])>.2:raise RuntimeError('Exact bed-facing standing cell was not reached')
    if tuple(foot)in rows or tuple(head)in rows:raise RuntimeError('Bed target changed while approaching')
    for e in q.get('scan_entities',[]):
        bounds=e.get('bounds')or{}
        if not bounds or any(all(bounds['max'][i]>cell[i]and bounds['min'][i]<cell[i]+1 for i in range(3))for cell in (foot,head)):
            raise RuntimeError('Entity entered the bed placement cells; no use sent')
    scope=hashlib.sha256((c.server+'|'+str(foot)).encode()).hexdigest()[:24];home=Path(c.root)/'village-beds'/scope;home.mkdir(parents=True,exist_ok=True);pointer=home/'active.json'
    if pointer.exists():
        prior=json.loads(Path(json.loads(pointer.read_text())['journal']).read_text())
        if not prior.get('complete')or prior.get('pending'):raise RuntimeError('Original bed placement is unresolved; no repeated use')
    out=Path(out);out.mkdir(exist_ok=False);path=out/'bed.json';before=inventory_counts(q)
    support=[foot[0],foot[1]-1,foot[2]];support_state=rows[tuple(support)]['state']
    book={'world_session':c.world,'foot':foot,'head':head,'facing':facing,'before':dict(before),'complete':False,
          'pending':{'op':'interact','support':support,'expected_state':support_state,'item':item}}
    write_json(path,book);write_json(pointer,{'journal':str(path.resolve())});previous=c.last
    try:reply=c.checked('interact',pos=support,face='up',expected_state=support_state,expected_hand=item)
    finally:book['pending']['request_id']=c.last if c.last!=previous else None;write_json(path,book)
    expected=before.copy();expected[item]-=1;expected=+expected;times=[];deadline=time.monotonic()+6
    while True:
        after,observed=survey()
        if(matches(observed.get(tuple(foot)),item,'foot',facing)and matches(observed.get(tuple(head)),item,'head',facing)
                and inventory_counts(after)==expected):
            if not times or after['time']>times[-1]:times.append(after['time'])
            if len(times)>=2:break
        else:times=[]
        if time.monotonic()>deadline:raise RuntimeError('Original bed use lacks both halves and exact one-bed debit; no replay')
        time.sleep(.1)
    book.update(complete=True,pending=None,placed=True,after=dict(expected),observed_times=times,receipt=reply,
                proof_scope='ordinary_bed_use_both_client_world_halves_and_exact_stock_debit_in_two_later_frames')
    write_json(path,book);return book
