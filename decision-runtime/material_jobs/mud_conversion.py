"""Install real downward dripstone under an existing, explicitly selected mud bed.

Never treats sulfur spikes, old client aliases or placement as clay production.
The caller owns the sole guarded controller and the full scan receipts.
"""
import time,math
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from projection_completion import block_state
from .local_air_path import move
from .navigation import settled_state
from .acquisition import _scan, _safe, block_id
from work_access import ApproachUnavailable

ITEM='minecraft:pointed_dripstone'

def pre_use_rejected(reply):
    return reply.get('phase')=='error' and reply.get('detail')=='Target interaction face is occluded or out of reach'


def column(rows, mud, *, top_id='minecraft:mud'):
    cells={tuple(b['pos']):b for b in rows}
    x,y,z=mud
    top=cells.get((x,y,z));support=cells.get((x,y-1,z));tip=cells.get((x,y-2,z))
    if (top_id not in ('minecraft:mud','minecraft:clay') or not top or block_id(top)!=top_id or top.get('fluid')is not False
            or not support or support.get('solid')is not True
            or support.get('fluid')is not False or support.get('block_entity')is not False):return None
    if tip is not None:
        _,properties=block_state(tip['state'])
        if (block_id(tip)==ITEM and properties.get('vertical_direction')=='down'
                and properties.get('waterlogged')=='false' and properties.get('thickness')=='tip'):
            return {'mud':list(mud),'support':support,'tip':tip,'ready':True}
        return None
    return {'mud':list(mud),'support':support,'tip_pos':[x,y-2,z],'ready':False}


def side_stations(rows,mud):
    """Player body stays beside the new spike, never occupying its placement cell."""
    cells={tuple(b['pos']) for b in rows};x,y,z=mud;result=[]
    for dx,dz in ((-1,0),(1,0),(0,-1),(0,1),(-2,0),(2,0),(0,-2),(0,2)):
        sx,sz=x+dx,z+dz
        if all((sx,h,sz)not in cells for h in (y-4,y-3,y-2)):
            result.append([sx+.5,y-3+.2,sz+.5])
    return result


def refill_column(rows,mud):
    cells={tuple(b['pos']):b for b in rows};x,y,z=mud
    top=cells.get(tuple(mud));support=cells.get((x,y-1,z));tip=cells.get((x,y-2,z))
    if (not support or support.get('solid')is not True or support.get('fluid')is not False
            or support.get('block_entity')is not False or not tip or block_id(tip)!=ITEM):return None
    _,props=block_state(tip['state'])
    if props!={'thickness':'tip','vertical_direction':'down','waterlogged':'false'}:return None
    if top and block_id(top)not in ('minecraft:mud','minecraft:clay'):return None
    return {'mud':list(mud),'support':support,'tip':tip,'filled':top is not None}


def refill(c,mud,out,checkpoint):
    """Replace only harvested air with carried mud; keep the actual base/tip."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'mud-refill.json'
    if path.exists():raise RuntimeError('Original refill retained; no replay')
    def state():checkpoint();q=c.status();_safe(q);return q
    def observe():
        x,y,z=mud;return _scan(c,[x,y-2,z],mud,state)
    original=refill_column(observe(),mud)
    if original is None:raise RuntimeError('Refill column changed or true tip is absent; preserve current blocks')
    if original['filled']:return {'mud':mud,'already_filled':True,'inventory_consumed':0}
    before=inventory_counts(state()).get('minecraft:mud',0)
    if not before:raise RuntimeError('No actual carried mud for refill')
    pose=[mud[0]+.5,mud[1]+1.2,mud[2]+.5]
    move(c,pose,out/'above-refill',max_straight=8,foot_offset=.2);settled_state(c,pose,.45)
    c.checked('select_item',item='minecraft:mud')
    fresh=refill_column(observe(),mud)
    if (not fresh or fresh['filled'] or fresh['support']['state']!=original['support']['state']
            or fresh['tip']['state']!=original['tip']['state']):raise RuntimeError('Refill bed changed before interaction')
    book={'world_session':c.world,'mud':mud,'inventory_before':before,'pending':True};write_json(path,book)
    try:
        c.checked('interact',pos=original['support']['pos'],face='up',
                  expected_state=original['support']['state'],expected_hand='minecraft:mud')
    finally:book['request_id']=c.last;write_json(path,book)
    until=time.monotonic()+5
    while True:
        current=refill_column(observe(),mud);after=inventory_counts(state()).get('minecraft:mud',0)
        if (current and current['filled'] and after==before-1
                and current['support']['state']==original['support']['state']
                and current['tip']['state']==original['tip']['state']):break
        if time.monotonic()>=until:raise RuntimeError('Mud refill conservation unconfirmed; no repeated placement')
        time.sleep(.15)
    book.update(pending=False,inventory_after=after,support_preserved=True,tip_preserved=True)
    write_json(path,book);return book


def install(c,mud,out,checkpoint):
    """One placement; exact current block states and inventory consumption required."""
    if not isinstance(mud,list)or len(mud)!=3 or any(type(v)is not int for v in mud):
        raise ValueError('Explicit integer mud coordinate required')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'installation.json'
    if path.exists():raise RuntimeError('Original dripstone placement retained; no replay')
    world=c.world
    def state():
        checkpoint();q=c.status();_safe(q)
        if q['world_session']!=world:raise RuntimeError('Mud bed world changed')
        return q
    def observe():
        x,y,z=mud
        return _scan(c,[x,y-2,z],mud,state)
    original=column(observe(),mud)
    if original is None:raise RuntimeError('Current mud/full support/empty tip column is unconfirmed')
    if original['ready']:return {'already_ready':True,'inventory_consumed':0,'clay_produced':False}
    before=inventory_counts(state()).get(ITEM,0)
    if before<1:raise RuntimeError('No actual pointed dripstone carried; sulfur is not a substitute')
    support=original['support']
    x,y,z=mud
    rows=_scan(c,[x-3,y-5,z-3],[x+3,y+1,z+3],state)
    poses=side_stations(rows,mud)
    if not poses:raise RuntimeError('No scanned side pose outside the new dripstone cell')
    book={'world_session':world,'mud':mud,'support':support,'tip_pos':original['tip_pos'],
          'inventory_before':before,'pending':True,'clay_produced':False}
    write_json(path,book)
    def pre_use():
        fresh=column(observe(),mud)
        if (fresh is None or fresh['ready'] or fresh['support']['state']!=support['state']
                or inventory_counts(state()).get(ITEM,0)!=before):
            raise RuntimeError('Mud bed or actual dripstone changed before placement')
    try:
        poses.sort(key=lambda p:math.dist(p,state()['pos']))
        for index,pose in enumerate(poses[:4]):
            move(c,pose,out/('side-access-%02d'%index),max_straight=3,foot_offset=.2)
            settled_state(c,pose,.45)
            c.checked('select_item',item=ITEM);pre_use()
            q=state();tip=original['tip_pos']
            if (abs(q['pos'][0]-(tip[0]+.5))<.81 and abs(q['pos'][2]-(tip[2]+.5))<.81):
                raise RuntimeError('Player overlaps the intended spike; no interaction sent')
            reply=c.request('interact',pos=support['pos'],face='down',
                            expected_state=support['state'],expected_hand=ITEM)
            book.setdefault('attempts',[]).append({'pose':pose,'request_id':c.last,
                'phase':reply.get('phase'),'detail':reply.get('detail')})
            write_json(path,book)
            if reply.get('phase')=='done':break
            if not pre_use_rejected(reply):raise RuntimeError(reply.get('detail','Dripstone interaction unconfirmed'))
        else:
            book.update(pending=False,placement_dispatched=False);write_json(path,book)
            raise ApproachUnavailable('No visible lower face from the four proved side poses')
    finally:
        book['request_id']=c.last;write_json(path,book)
    deadline=time.monotonic()+5
    while True:
        q=state();seen=observe();fresh=column(seen,mud)
        actual_tip=next((b for b in seen if b['pos']==original['tip_pos']),None)
        top=next((b for b in seen if b['pos']==mud),None)
        converted=top is not None and block_id(top)=='minecraft:clay'
        after=inventory_counts(state()).get(ITEM,0)
        if actual_tip and block_id(actual_tip)==ITEM and (fresh and fresh['ready'] or converted) and after==before-1:break
        if time.monotonic()>=deadline:
            raise RuntimeError('Dripstone placement or consumption uncertain; no second placement')
        time.sleep(.15)
    book.update(pending=False,inventory_after=after,tip_state=actual_tip['state'],
                native_placement_verified=True,clay_produced=converted)
    write_json(path,book);return book


def harvest(c,mud,out,checkpoint):
    """One actual converted block yields four observed balls; base and tip remain."""
    from work_access import approach_faces
    from drop_collection import collect_drop
    from .acquisition import _tool,_choose_tool
    from material_trip_policy import room_for_item
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'clay-harvest.json'
    if path.exists():raise RuntimeError('Original clay harvest retained; no replay')
    def state():
        checkpoint();q=c.status();_safe(q);return q
    def observe():
        x,y,z=mud
        return _scan(c,[x,y-2,z],mud,state)
    original=column(observe(),mud,top_id='minecraft:clay')
    if not original or not original['ready']:raise RuntimeError('Actual converted clay/support/real tip unconfirmed')
    if room_for_item(state(),'minecraft:clay_ball')<4:raise RuntimeError('No backpack space for four real clay balls')
    face=approach_faces(c,mud,'Block{minecraft:clay}',('up',),seconds=45,stand_distance=1.2)
    tool=_tool(state(),'shovel',33)
    if any(e.get('id')=='minecraft:silk_touch' for e in tool.get('enchantments',[])):
        raise RuntimeError('Non-silk shovel required for four clay balls')
    _choose_tool(c,tool,state)
    fresh=column(observe(),mud,top_id='minecraft:clay')
    if not fresh or not fresh['ready'] or fresh['support']['state']!=original['support']['state']:
        raise RuntimeError('Converted farm column changed before mining')
    before_state=state();before=inventory_counts(before_state).get('minecraft:clay_ball',0)
    old={e['uuid'] for e in before_state.get('entities',[])if e.get('type')=='minecraft:item'}
    book={'world_session':c.world,'mud':mud,'support':original['support'],'tip':original['tip'],
          'before':before,'pending':True};write_json(path,book)
    try:c.checked('mine_block',pos=mud,face=face,expected_state='Block{minecraft:clay}',seconds=20)
    finally:book['request_id']=c.last;write_json(path,book)
    q=state()
    if inventory_counts(q).get('minecraft:clay_ball',0)==before:
        drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'
               and e.get('stack',{}).get('item')=='minecraft:clay_ball' and e.get('uuid')not in old
               and math.dist(e['pos'],mud)<6]
        if len(drops)!=1 or drops[0]['stack']['count']!=4 or not collect_drop(c,drops[0],q):
            raise RuntimeError('Four new clay balls not exactly identified or collected; no mining replay')
    rows=observe();cells={tuple(b['pos']):b for b in rows};x,y,z=mud
    after=inventory_counts(state()).get('minecraft:clay_ball',0)
    if (tuple(mud)in cells or after!=before+4
            or cells.get((x,y-1,z),{}).get('state')!=original['support']['state']
            or cells.get((x,y-2,z),{}).get('state')!=original['tip']['state']):
        raise RuntimeError('Farm harvest conservation or retained support/tip unconfirmed')
    book.update(pending=False,after=after,actual_clay_balls_gained=4,support_preserved=True,tip_preserved=True)
    write_json(path,book);return book
