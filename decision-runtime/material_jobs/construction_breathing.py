"""Interrupt dry construction on submersion; never wait underwater for cleanup."""
import math
from pathlib import Path

from kit_runtime.journal import write_json
from .protocol import JobBlocked, JobPaused


def _owned(c, state):
    lease = state.get('supervision_lease') or {}
    return (state.get('connected') is True and state.get('world_session') == c.world
            and not state.get('manual_movement') and not state.get('screen')
            and not (state.get('safety_hold') or {}).get('active')
            and lease.get('kind') == 'materials' and lease.get('job_session') == c.task
            and lease.get('id') == c.heartbeat.id and lease.get('world_session') == c.world
            and lease.get('revision') == state.get('control_revision') == c.rev)


def vertical_air_target(position, reply, world, rise=12):
    """Only ordinary air/water in the entire current body column may be crossed."""
    x, y, z = position
    low = [math.floor(x-.31), math.floor(y), math.floor(z-.31)]
    high = [math.floor(x+.31), math.floor(y)+rise+1, math.floor(z+.31)]
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != world
            or reply.get('scan_cells_read') != math.prod(b-a+1 for a,b in zip(low,high))
            or not isinstance(reply.get('blocks'), list)):
        return None
    cells = {}
    for row in reply['blocks']:
        pos = row.get('pos')
        if (not isinstance(pos,list) or len(pos)!=3 or any(type(n) is not int for n in pos)
                or not all(low[i]<=pos[i]<=high[i] for i in range(3)) or tuple(pos) in cells):
            return None
        cells[tuple(pos)] = row
    water = {'Block{minecraft:water}[level='+str(n)+']' for n in range(16)}
    for floor in range(low[1]+1, low[1]+rise+1):
        dry = True
        for bx in range(low[0], high[0]+1):
            for bz in range(low[2], high[2]+1):
                for by in range(low[1], floor+2):
                    row = cells.get((bx,by,bz))
                    if row is None: continue  # Native complete sparse scan omits only air.
                    if (row.get('block_entity') or row.get('solid') is not False
                            or row.get('state') not in water | {'Block{minecraft:air}'}):
                        return None
                    if by >= floor and row.get('state') != 'Block{minecraft:air}': dry = False
        if dry: return [x, floor+.05, z]
    return None


def interrupt_submerged(c, state, out):
    """Return False when dry; submerged calls always stop this construction batch."""
    if state.get('under_water') is not True: return False
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    if not _owned(c,state): raise JobPaused('水下施工控制已交还，不发送换气或退出操作')
    job = state.get('build_job') or {}
    if job.get('active'):
        c.checked('build_control', job_session=job['session'], action='pause_and_report')
    fresh = c.status()
    if not _owned(c,fresh): raise JobPaused('暂停施工后控制已改变，保留现场')
    if not fresh.get('under_water'): raise JobBlocked('水下施工已停止，重新核验干燥站位后继续')
    proof = {'world_session':c.world, 'task_session':c.task, 'pos':fresh['pos'],
             'air_supply':fresh.get('air_supply'), 'resource_actions_replayed':False,
             'goal_completion_credit':0, 'dry_return_confirmed':False,
             'interrupted_build':state.get('build_job'),
             'interrupted_printer':state.get('professional_printer')}
    write_json(out/'construction-breathing.json',proof)
    target = None
    if (fresh.get('health',0)>=19 and fresh.get('air_supply',0)>=245
            and fresh.get('air_return_protocol')==1 and fresh.get('oxygen_bonus',0)>=3
            and fresh.get('auto_log') is True and fresh.get('flight') is True):
        x,y,z = fresh['pos']
        low=[math.floor(x-.31),math.floor(y),math.floor(z-.31)]
        high=[math.floor(x+.31),math.floor(y)+13,math.floor(z+.31)]
        reply=c.request('scan',min=low,max=high,details=True)
        target=vertical_air_target(fresh['pos'],reply,c.world)
    current=c.status()
    if not _owned(c,current): raise JobPaused('换气前控制已改变，保留现场')
    if (math.dist(current['pos'],fresh['pos'])>.2 or current.get('air_supply',0)<245
            or current.get('health',0)<19): target=None
    # No guessed route through a ceiling; low air also cannot justify a new dive.
    if target is None:
        proof['action']='safe_logout_no_verified_air_route';write_json(out/'construction-breathing.json',proof)
        previous=getattr(c,'last',None);requested=False
        try:
            c.request('safe_logout');requested=True
        finally:
            if requested or getattr(c,'last',None)!=previous:
                from safety_interlock import record_material_health_exit
                record_material_health_exit(c.root,current,'Construction submerged without a verified air route')
        raise JobBlocked('水下施工没有已核验退路，已请求安全退出；不自动重连')
    c.checked('air_return_set',target=target)
    proof.update(action='verified_vertical_air_return',target=target);write_json(out/'construction-breathing.json',proof)
    reply=c.request('navigate',target=target,arrival=.2,seconds=20)
    actual=c.status()
    if (not _owned(c,actual) or reply.get('phase')!='done'
            or actual.get('under_water') or actual.get('air_supply',0)<245
            or math.dist(actual['pos'],target)>.7):
        raise JobBlocked('换气动作尚未核验，保留原动作与原生返气防护，不继续施工')
    proof.update(dry_return_confirmed=True,actual_pos=actual['pos'],actual_air=actual['air_supply'])
    write_json(out/'construction-breathing.json',proof)
    raise JobBlocked('已退回干燥位置；本批水下站位需重新规划，未重放放置')


def lift_surface_feet(c, state):
    """Lift out of observed foot-level water before planning a dry air route."""
    if (not _owned(c,state) or state.get('under_water') or state.get('health',0)<19
            or state.get('air_supply',0)<285 or not state.get('flight')
            or state.get('guard_busy') or state.get('navigating')):
        raise JobPaused('水面抬升的当前控制、氧气或防护未确认')
    x,y,z=state['pos'];low=[math.floor(x-.31),math.floor(y),math.floor(z-.31)]
    high=[math.floor(x+.31),math.floor(y)+13,math.floor(z+.31)]
    reply=c.request('scan',min=low,max=high,details=True)
    # Reuse complete-column validation, then require the extra head cell for
    # a .5-block dry-foot margin. No adjacent water or roof voxel is ignored.
    target=vertical_air_target(state['pos'],reply,c.world)
    if target is None:raise JobBlocked('水面上方没有已确认的普通水/空气退路')
    floor=math.floor(target[1]);water={'Block{minecraft:water}[level='+str(n)+']' for n in range(16)}
    rows=reply['blocks']
    if not any(row['pos'][1]==low[1] and row.get('state')in water for row in rows):
        raise JobBlocked('当前脚部未观察到普通流水，不执行水面抬升')
    if floor+2>high[1] or any(row['pos'][1]==floor+2 and row.get('state')!='Block{minecraft:air}'for row in rows):
        raise JobBlocked('抬升后的完整身体净空不足，不穿过顶棚')
    target=[x,floor+.5,z];fresh=c.status()
    if not _owned(c,fresh) or math.dist(fresh['pos'],state['pos'])>.15:
        raise JobPaused('水面扫描后角色或控制改变，不沿旧列移动')
    out=Path(c.out)/'surface-feet-lift.json';book={'world_session':c.world,'task_session':c.task,
        'from':state['pos'],'target':target,'pending':True,'complete':False,
        'resource_actions_replayed':False,'goal_completion_credit':0}
    write_json(out,book)
    try:
        # Air-only navigation rejects the water at the starting feet. Ordinary
        # native navigation still checks real collisions and makes no block edits.
        result=c.request('navigate',target=target,arrival=.15,seconds=15)
    finally:
        book['request_id']=getattr(c,'last',None);write_json(out,book)
    actual=c.status()
    if (result.get('phase')!='done' or not _owned(c,actual) or actual.get('under_water')
            or actual.get('air_supply',0)<260 or actual.get('health',0)<19
            or actual['pos'][1]<floor+.1 or math.dist(actual['pos'],target)>.7):
        raise JobBlocked('脚部抬升未得到实际干燥站位确认，保留原动作不重试')
    book.update(pending=None,complete=True,actual=actual['pos']);write_json(out,book)
    return actual
