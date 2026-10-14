"""One ordinary bone-meal use on a live natural rose mother; never breaks it."""
import time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from drop_collection import collect_drop
from work_access import approach_faces
from .acquisition import _scan,_safe,block_id,NATURAL
from .colored_sources import _protected,_stage_source
from .renewable_flowers import SOFT

ITEM='minecraft:rose_bush'
FLOWERS={'minecraft:'+n for n in ('rose_bush','lilac','peony','sunflower','orange_tulip','red_tulip')}
SOIL={'minecraft:'+n for n in ('grass_block','dirt','coarse_dirt','rooted_dirt','podzol','mycelium')}


def mother(rows,pos):
    cells={tuple(b['pos']):b for b in rows};x,y,z=pos
    lower=cells.get((x,y,z));upper=cells.get((x,y+1,z));floor=cells.get((x,y-1,z))
    if (not lower or not upper or not floor or block_id(lower)!=ITEM or block_id(upper)!=ITEM
            or 'half=lower'not in lower['state'] or 'half=upper'not in upper['state']
            or block_id(floor)not in SOIL or floor.get('solid')is not True):return None
    for b in rows:
        name=block_id(b)
        if (b.get('fluid')is not False or b.get('block_entity')is not False
                or name not in NATURAL|SOFT|FLOWERS
                and not name.endswith(('_leaves','_log'))):return None
    return lower,upper


def grow(c,pos,profile,out,checkpoint):
    if not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos):
        raise ValueError('Explicit integer rose mother coordinates required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'rose-bone-meal.json'
    if path.exists():raise RuntimeError('Original rose use intent is retained; no replay')
    world=c.world
    def state():
        checkpoint();q=c.status();_safe(q)
        if q['world_session']!=world or q.get('guard_busy')or _protected(pos,profile,q):
            raise RuntimeError('Rose mother world, protection or action ownership changed')
        return q
    def scan():return _scan(c,[pos[0]-2,pos[1]-1,pos[2]-2],
                            [pos[0]+2,pos[1]+3,pos[2]+2],state)
    original=mother(scan(),pos)
    if original is None:raise RuntimeError('Current natural two-block rose mother is unconfirmed')
    _stage_source(c,pos,state)
    face=approach_faces(c,pos,original[0]['state'],('north','south','east','west','up'),seconds=45)
    fresh=mother(scan(),pos)
    if fresh is None or [b['state']for b in fresh]!=[b['state']for b in original]:
        raise RuntimeError('Rose mother changed during approach; bone meal not sent')
    c.checked('select_item',item='minecraft:bone_meal')
    before=state();counts=inventory_counts(before)
    if counts.get('minecraft:bone_meal',0)<=16:raise RuntimeError('Retain sixteen bone meal for remaining map dyes')
    old={e['uuid']:e.get('stack')for e in before.get('entities',[])if e.get('type')=='minecraft:item'
         and e.get('stack',{}).get('item')==ITEM and isinstance(e.get('uuid'),str)}
    book={'world_session':world,'pos':pos,'mother_states':[b['state']for b in fresh],
          'bone_before':counts.get('minecraft:bone_meal',0),'rose_before':counts.get(ITEM,0),
          'old_drops':old,'pending':{'kind':'bone_meal_use'},'mother_removed':False}
    write_json(path,book)
    try:
        reply=c.request('interact',pos=pos,face=face,expected_state=fresh[0]['state'],
                        expected_hand='minecraft:bone_meal')
    finally:
        book['pending']['request_id']=c.last;write_json(path,book)
    rid=c.last
    if reply.get('id')!=rid or reply.get('world_session')!=world or reply.get('phase')!='done':
        raise RuntimeError('Rose use has no exact completed native reply; preserve intent')
    deadline=time.monotonic()+6
    while inventory_counts(state()).get('minecraft:bone_meal',0)==book['bone_before']and time.monotonic()<deadline:
        time.sleep(.15)
    q=state();after=inventory_counts(q)
    if after.get('minecraft:bone_meal',0)!=book['bone_before']-1:
        raise RuntimeError('Exact bone meal consumption is unconfirmed; never repeat')
    live=mother(scan(),pos)
    if live is None or [b['state']for b in live]!=book['mother_states']:
        raise RuntimeError('Rose mother preservation is unconfirmed')
    if after.get(ITEM,0)==book['rose_before']:
        new=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'
             and e.get('stack',{}).get('item')==ITEM and e.get('stack',{}).get('count')==1
             and isinstance(e.get('uuid'),str)and e['uuid']not in old]
        if len(new)!=1:raise RuntimeError('One new rose drop not identified; preserve use without replay')
        book['pending']={'kind':'pickup','uuid':new[0]['uuid'],'use_request_id':rid};write_json(path,book)
        if not collect_drop(c,new[0],q):raise RuntimeError('New rose pickup remains unconfirmed')
    q=state();after=inventory_counts(q);live=mother(scan(),pos)
    if (after.get(ITEM,0)!=book['rose_before']+1 or after.get('minecraft:bone_meal',0)!=book['bone_before']-1
            or live is None or [b['state']for b in live]!=book['mother_states']):
        raise RuntimeError('Rose growth final conservation differs; no replay')
    book.update(pending=None,bone_after=after['minecraft:bone_meal'],rose_after=after[ITEM],
                native_reply=reply,gained=1,mother_preserved=True)
    write_json(path,book);return book


def planting_site(rows,pos):
    cells={tuple(b['pos']):b for b in rows};x,y,z=pos
    ground=cells.get((x,y-1,z))
    return (ground is not None and block_id(ground)in SOIL and ground.get('solid')is True
            and ground.get('fluid')is False and ground.get('block_entity')is False
            and (x,y,z)not in cells and (x,y+1,z)not in cells)


def plant(c,pos,profile,out,checkpoint):
    """Plant one carried mother through ordinary interaction on dry natural soil."""
    if not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos):
        raise ValueError('Explicit integer mother planting position required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'rose-planting.json'
    if path.exists():raise RuntimeError('Original mother planting is retained; no replay')
    ground=[pos[0],pos[1]-1,pos[2]]
    def state():
        checkpoint();q=c.status();_safe(q)
        if _protected(pos,profile,q)or q.get('guard_busy'):
            raise RuntimeError('Mother planting footprint or action protection changed')
        return q
    def scan():return _scan(c,[pos[0]-1,pos[1]-1,pos[2]-1],
                            [pos[0]+1,pos[1]+2,pos[2]+1],state)
    rows=scan()
    if not planting_site(rows,pos):raise RuntimeError('Mother planting needs real dry soil and two empty cells')
    _stage_source(c,ground,state)
    soil=next(b for b in rows if b['pos']==ground)
    face=approach_faces(c,ground,soil['state'],('up',),seconds=45)
    c.checked('select_item',item=ITEM)
    rows=scan();before=inventory_counts(state()).get(ITEM,0)
    if before<1 or not planting_site(rows,pos):raise RuntimeError('Actual mother item or planting cells changed')
    soil=next(b for b in rows if b['pos']==ground)
    book={'world_session':c.world,'pos':pos,'before':before,'pending':True};write_json(path,book)
    reply=c.request('interact',pos=ground,face=face,expected_state=soil['state'],expected_hand=ITEM)
    rid=c.last;book['request_id']=rid;write_json(path,book)
    if reply.get('id')!=rid or reply.get('world_session')!=c.world or reply.get('phase')!='done':
        raise RuntimeError('Mother planting has no exact owned completion; no replay')
    deadline=time.monotonic()+6
    while True:
        q=state();rows=scan();live=mother(rows,pos);after=inventory_counts(q).get(ITEM,0)
        if live and after==before-1:break
        if after not in (before,before-1)or time.monotonic()>=deadline:
            raise RuntimeError('Mother halves and exact item consumption not jointly confirmed; no replay')
        time.sleep(.15)
    book.update(pending=False,after=after,mother_states=[b['state']for b in live],
                native_reply=reply,planted=True,inventory_credit=0)
    write_json(path,book);return book
