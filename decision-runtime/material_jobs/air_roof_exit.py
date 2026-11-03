"""Leave an overhead roof through a freshly proved horizontal flight corridor.

This does not mine, lower the player to ground, waive native collision checks,
or retry a submitted navigation. A roof above an airborne builder is not a tree.
"""
import math,time
from kit_runtime.journal import write_json
from .protocol import JobBlocked


def candidates(position):
    x,y,z=position
    return [[math.floor(x+dx)+.5,y,math.floor(z+dz)+.5]
            for radius in (4,8,12,20,28)
            for dx,dz in ((radius,0),(-radius,0),(0,radius),(0,-radius))]


def escape(client,state):
    if state.get('flight') is not True or state.get('on_ground') is True:
        return None
    from .navigation import _air_scan,_body_sweep,settled_state
    from .acquisition import _safe
    def current():
        q=settled_state(client);_safe(q)
        if (q.get('world_session')!=client.world or q.get('health',0)<19
                or q.get('manual_movement') or q.get('screen') or q.get('under_water')
                or q.get('guard_busy') or not q.get('guard_armed')
                or not q.get('guard_pve_only') or not q.get('flight')
                or q.get('air_only_navigation_protocol',0)<2):
            raise JobBlocked('空中屋顶绕行的世界、健康或飞行防护状态变化')
        return q
    original=current()['pos']
    if math.dist(original,state['pos'])>.3:
        raise JobBlocked('空中屋顶绕行起点已变化，未移动')
    for target in candidates(original):
        low,high=_body_sweep(target,target);low[1]=-64;high[1]=319
        column=_air_scan(client,low,high)
        if not column:continue
        top=max((r['pos'][1]+1 for r in column if r.get('fluid') or not r.get('passable',True)),default=None)
        if top is None or top>=original[1] or top+24>=319:continue
        low,high=_body_sweep(original,target)
        if math.prod(high[i]-low[i]+1 for i in range(3))>50000:continue
        if _air_scan(client,low,high):continue
        fresh=current()
        if math.dist(fresh['pos'],original)>.3:
            raise JobBlocked('屋顶空气通道核验期间起点变化，未移动')
        path=client.out/('air-roof-exit-%d.json'%time.time_ns())
        book={'world_session':client.world,'from':original,'target':target,
              'pending':True,'column_top':top,'parking_confirmed':False,
              'mining_sent':False,'ground_walk_sent':False,'automatic_retry_allowed':False}
        write_json(path,book)
        try:client.checked('navigate',target=target,arrival=.25,air_only=True,seconds=45)
        finally:
            book['request_id']=getattr(client,'last',None);write_json(path,book)
        final=current()
        if math.dist(final['pos'],target)>.6:
            raise JobBlocked('屋顶空气绕行实际位置尚未确认；保留原请求，不重发')
        # The caller must re-scan the actual full body column before parking.
        book.update(pending=False,actual=final['pos']);write_json(path,book)
        return final
    raise JobBlocked('上方屋顶附近没有已核验的本地空气出口')
