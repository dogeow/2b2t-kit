"""Enter the native fixed-tree controller from a real grounded walking pose.

Starting in Flight can repeatedly restore hovering during the native standby
landing. A normal short walk keeps Flight off, as other grounded work does.
"""
import math,time
from kit_runtime.journal import write_json
from .protocol import JobBlocked

FLOORS={'minecraft:grass_block','minecraft:dirt','minecraft:coarse_dirt','minecraft:rooted_dirt',
        'minecraft:podzol','minecraft:stone','minecraft:cobblestone','minecraft:deepslate','minecraft:moss_block'}

def ready(q):return q.get('on_ground')is True and q.get('flight')is False

def prepare(c,checkpoint):
    checkpoint();q=c.status()
    lease=q.get('supervision_lease')or{}
    if(q.get('world_session')!=c.world or q.get('health',0)<19 or q.get('manual_movement')or q.get('screen')
            or q.get('guard_busy')or not q.get('guard_armed')or not q.get('guard_pve_only')
            or q.get('under_water')or q.get('chopping')or lease.get('job_session')!=c.task):
        raise JobBlocked('固定树砍伐需要当前健康、空闲且可正常落地的材料角色')
    if ready(q):return q
    pos=q['pos'];y=round(pos[1])
    if abs(pos[1]-y)>.25:raise JobBlocked('固定树交接前需先到达已验证地面附近')
    low=[math.floor(pos[0]-.31),y-1,math.floor(pos[2]-.31)];high=[math.floor(pos[0]+.31),y+1,math.floor(pos[2]+.31)]
    scan=c.checked('scan',min=low,max=high,details=True)
    if scan.get('scan_cells_read')!=scan.get('scan_total_cells'):raise JobBlocked('固定树落脚格尚未完整核验')
    rows={tuple(r['pos']):r for r in scan['blocks']}
    for x in range(low[0],high[0]+1):
        for z in range(low[2],high[2]+1):
            floor=rows.get((x,y-1,z),{})
            name=floor.get('state','').split('}',1)[0].removeprefix('Block{')
            if name not in FLOORS or not floor.get('solid')or floor.get('fluid')or floor.get('block_entity'):
                raise JobBlocked('固定树正常落地需要完整干燥自然地面')
            for h in (y,y+1):
                if (x,h,z)in rows:raise JobBlocked('固定树落地身体空间存在方块，未发送走路')
    path=c.out/('fixed-tree-ground-'+str(time.time_ns())+'.json')
    book={'world_session':c.world,'before':{k:q.get(k)for k in ('pos','on_ground','flight')},'pending':'ordinary_ground_walk','complete':False}
    write_json(path,book);previous=c.last
    try:reply=c.checked('walk',target=[pos[0],float(y),pos[2]],arrival=.12,seconds=8,restore_flight=False)
    finally:book['request_id']=c.last if c.last!=previous else None;write_json(path,book)
    observed=[];deadline=time.monotonic()+3
    while True:
        checkpoint();actual=c.status()
        if actual.get('world_session')!=c.world:raise JobBlocked('固定树落地期间切换世界，保留原动作')
        if ready(actual)and math.dist(actual['pos'],[pos[0],float(y),pos[2]])<=.25:
            if not observed or actual['time']>observed[-1]:observed.append(actual['time'])
            if len(observed)>=2:break
        else:observed=[]
        if time.monotonic()>deadline:raise JobBlocked('正常走路后仍未实际落地，未开始砍树')
        time.sleep(.1)
    book.update(complete=True,pending=None,receipt=reply,observed_times=observed,
                actual={k:actual.get(k)for k in ('pos','on_ground','flight')},mode='grounded_work_until_next_owned_flight')
    write_json(path,book);return actual
