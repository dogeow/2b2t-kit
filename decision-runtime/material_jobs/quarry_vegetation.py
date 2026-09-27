"""Clear only observed wild grass above an authorized natural shaft entrance.

Plants have no collision but still intercept Minecraft's real mining ray. This
uses ordinary confirmed block interactions, not an ignored or synthetic ray.
"""
import hashlib
import json
import math
from pathlib import Path

from kit_runtime.journal import write_json


def clear_entrance(c, region, low, high, checkpoint):
    from .acquisition import Unavailable, _safe, _scan, block_id
    from .discovery import WILD_GRASS

    shaft = region.get('access_shaft') or {}
    top = region.get('surface_y')
    if region.get('source') != 'natural_survey' or type(top) is not int or high[1] != top:
        return 0
    a, b = shaft.get('min'), shaft.get('max')
    if (not isinstance(a,list) or not isinstance(b,list) or len(a)!=3 or len(b)!=3
            or b[1]!=top or not all(low[i]==a[i] and high[i]==b[i] for i in (0,2))
            or high[0]-low[0]!=1 or high[2]-low[2]!=1):
        raise Unavailable('清理野草需要当前自然入口的准确边界')
    lo, hi = [low[0],top+1,low[2]], [high[0],top+2,high[2]]
    scope = hashlib.sha256(json.dumps([c.world,lo,hi]).encode()).hexdigest()[:24]
    path = Path(c.root).parent/'quarry-entrance-clearing'/(scope+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    journal = json.loads(path.read_text()) if path.exists() else {'world_session':c.world,'attempts':[]}
    if journal.get('world_session') != c.world or any(r.get('state')=='inflight' for r in journal['attempts']):
        raise Unavailable('入口野草前次挖掘回执不确定，不能重复发送')
    removed=0
    for _ in range(8):
        _safe(c.status())
        rows=_scan(c,lo,hi,checkpoint)
        if not rows:return removed
        if any(not all(lo[i]<=r['pos'][i]<=hi[i] for i in range(3))
               or block_id(r) not in WILD_GRASS or not r.get('passable')
               or r.get('fluid') or r.get('block_entity') for r in rows):
            raise Unavailable('自然入口上方有需保留的植物或其它方块，不自动清除')
        row=max(rows,key=lambda r:r['pos'][1])
        state=c.status();_safe(state)
        eye=[state['pos'][0],state['pos'][1]+1.62,state['pos'][2]]
        if math.dist(eye,[v+.5 for v in row['pos']])>4.2:
            raise Unavailable('入口野草不在正常挖掘距离内，不隔空挖掘')
        entry={'state':'inflight','pos':row['pos'],'expected_state':row['state'],
               'observed_at':state.get('time')}
        journal['attempts'].append(entry);write_json(path,journal)
        previous=getattr(c,'last',None)
        try:
            reply=c.request('mine_block',pos=row['pos'],expected_state=row['state'],seconds=5)
        finally:
            if getattr(c,'last',None)!=previous:
                entry['request_id']=c.last;write_json(path,journal)
        if (reply.get('phase')!='done' or reply.get('id')!=entry.get('request_id')
                or reply.get('world_session')!=c.world):
            raise Unavailable('入口野草未获得本次挖掘确认，保留记录且不重放')
        fresh=_scan(c,row['pos'],row['pos'],checkpoint)
        if fresh:
            raise Unavailable('入口野草挖掘后方块仍存在，保留记录且不重放')
        entry.update(state='confirmed',confirmed_at=c.status().get('time'));write_json(path,journal)
        removed+=1
    if _scan(c,lo,hi,checkpoint):
        raise Unavailable('入口野草超过单次清理范围，停止继续挖掘')
    return removed
