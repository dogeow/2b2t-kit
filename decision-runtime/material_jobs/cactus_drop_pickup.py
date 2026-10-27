"""Recover one exact new cactus drop through surveyed air, never mine again."""
import math,time
from pathlib import Path
from material_plan import inventory_counts
from kit_runtime.journal import write_json
from .renewable_cactus import side_pose_clear
from .navigation import settled_state


class UnreceivedCactusDrop(RuntimeError):
    """Known mined item is absent; this is neither a pickup nor inventory credit."""
    def __init__(self, uuid):
        super().__init__('Exact original cactus drop is not currently available')
        self.uuid = uuid


def recover(c,pos,receipt,before,previous_entities,out,checkpoint):
    seq=receipt.get('native_sequence')
    if (receipt.get('phase')!='done' or receipt.get('world_session')!=c.world
            or receipt.get('mining_target')!=pos or receipt.get('server_confirmed')is not True
            or receipt.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
            or type(seq)is not int or seq<=0 or receipt.get('server_ack_sequence')!=seq):
        raise RuntimeError('Unknown cactus mining cannot authorize a pickup route')
    candidates=[e for e in receipt.get('entities',[])if e.get('type')=='minecraft:item'
        and e.get('uuid')not in previous_entities and isinstance(e.get('uuid'),str)
        and(e.get('stack')or{}).get('item')=='minecraft:cactus'and(e.get('stack')or{}).get('count')==1
        and isinstance(e.get('pos'),list)and math.dist(e['pos'],[v+.5 for v in pos])<=3]
    if len(candidates)!=1:raise RuntimeError('Exact new single cactus drop identity is not proved')
    uuid=candidates[0]['uuid'];out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'cactus-drop-pickup.json'
    if path.exists():raise RuntimeError('Original cactus pickup route retained; no replay')
    def current():
        checkpoint();q=c.status()
        if(q.get('world_session')!=c.world or q.get('health')!=20 or q.get('manual_movement')
                or q.get('screen')or q.get('guard_busy')):raise RuntimeError('Cactus pickup control or health changed')
        return q
    q=current();drop=next((e for e in q.get('entities',[])if e.get('uuid')==uuid),None)
    if drop is None and inventory_counts(q)['minecraft:cactus']==before:
        raise UnreceivedCactusDrop(uuid)
    if(drop is None or(drop.get('stack')or{}).get('item')!='minecraft:cactus'
            or(drop.get('stack')or{}).get('count')!=1 or inventory_counts(q)['minecraft:cactus']!=before):
        raise RuntimeError('Exact original cactus drop is not currently available')
    d=drop['pos'];y=math.floor(d[1])+.2;up=max(q['pos'][1],pos[1]+4.)
    low=[pos[0]-4,min(pos[1]-4,math.floor(d[1])-1),pos[2]-4]
    high=[pos[0]+4,max(pos[1]+6,math.ceil(up)+2),pos[2]+4]
    r=c.request('scan',min=low,max=high,details=True)
    cells=math.prod(b-a+1 for a,b in zip(low,high))
    if(r.get('id')!=c.last or r.get('world_session')!=c.world or r.get('phase')!='done'
            or r.get('scan_cells_read')!=cells or r.get('scan_total_cells')!=cells):
        raise RuntimeError('Drop side and descent column scan is incomplete')
    rows=r['blocks'];poses=[]
    for dx in(-1,0,1):
        for dz in(-1,0,1):
            p=[math.floor(d[0])+dx+.5,y,math.floor(d[2])+dz+.5]
            if math.hypot(p[0]-d[0],p[2]-d[2])>.95:continue
            if all(side_pose_clear(rows,low,high,[p[0],y+(up-y)*i/16,p[2]],tolerance=.1)for i in range(17)):
                poses.append(p)
    if not poses:raise RuntimeError('No observed cactus-free pickup and vertical column')
    pose=min(poses,key=lambda p:math.dist(p,d))
    book={'world_session':c.world,'original_mine':receipt['id'],'original_sequence':seq,
          'drop_uuid':uuid,'actual_drop':d,'before':before,'pose':pose,'pending':'air_route','mine_replayed':False}
    write_json(path,book)
    for point in([q['pos'][0],up,q['pos'][2]],[pose[0],up,pose[2]],pose):
        current();c.checked('navigate',target=point,arrival=.15,air_only=True,seconds=30)
        actual=settled_state(c,point,.4)
        if not side_pose_clear(rows,low,high,actual['pos'],tolerance=.05):
            raise RuntimeError('Actual cactus pickup pose leaves surveyed safe air')
    deadline=time.monotonic()+6;confirmed=0;stamp=-1
    while confirmed<2:
        q=current();after=inventory_counts(q)['minecraft:cactus']
        if after not in(before,before+1):raise RuntimeError('Cactus pickup inventory changed unexpectedly')
        good=after==before+1 and not any(e.get('uuid')==uuid for e in q.get('entities',[]))
        if good and q.get('time',0)>stamp:confirmed+=1;stamp=q.get('time',0)
        elif not good:confirmed=0
        if time.monotonic()>deadline:raise RuntimeError('Original cactus drop pickup still unproved; no mine replay')
        time.sleep(.15)
    book.update(pending=None,complete=True,after=after,actual_pose=q['pos'],health=q['health'])
    write_json(path,book);return q
