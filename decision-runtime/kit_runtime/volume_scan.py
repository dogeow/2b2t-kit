"""Compose bounded native sparse scans without calling partial coverage complete."""
import math
import time


class IncompleteVolumeScan(RuntimeError):
    pass


def complete_blocks(client, low, high):
    if (not isinstance(low,list) or not isinstance(high,list) or len(low)!=3 or len(high)!=3
            or any(type(n)is not int for n in low+high) or any(a>b for a,b in zip(low,high))):
        raise IncompleteVolumeScan('场景扫描需要完整整数边界')
    volume=math.prod(b-a+1 for a,b in zip(low,high))
    if volume>100000:raise IncompleteVolumeScan('完整场景扫描超过十万格上限')
    tiled=volume>50000;started=time.monotonic();scope=None
    if tiled:
        before=client.status();scope=(before.get('world_session'),before.get('control_revision'))
        if scope[0]!=client.world or type(scope[1])is not int:
            raise IncompleteVolumeScan('分片扫描缺少当前世界和控制版本')
    pending=[(list(low),list(high))];result=[]
    while pending:
        lo,hi=pending.pop();size=math.prod(b-a+1 for a,b in zip(lo,hi))
        if size>50000:
            axis=max(range(3),key=lambda i:hi[i]-lo[i]);mid=(lo[axis]+hi[axis])//2
            left_hi=list(hi);left_hi[axis]=mid;right_lo=list(lo);right_lo[axis]=mid+1
            pending.extend([(right_lo,hi),(lo,left_hi)]);continue
        reply=client.request('scan',min=lo,max=hi,details=True)
        if (reply.get('phase')not in(None,'done') or reply.get('world_session')!=client.world
                or not isinstance(reply.get('blocks'),list)):
            raise IncompleteVolumeScan('当前场景分片尚未完整确认')
        if tiled:
            if (type(reply.get('scan_cells_read'))is not int or reply['scan_cells_read']!=size
                    or any(type(reply.get(k))is not int for k in ('scan_start_revision','scan_end_revision'))
                    or reply.get('scan_start_revision')!=scope[1] or reply.get('scan_end_revision')!=scope[1]):
                raise IncompleteVolumeScan('分片覆盖数量或控制版本不一致')
            seen=set()
            for row in reply['blocks']:
                pos=row.get('pos')if isinstance(row,dict)else None
                if (not isinstance(pos,list) or len(pos)!=3 or any(type(n)is not int for n in pos)
                        or not all(lo[i]<=pos[i]<=hi[i]for i in range(3)) or tuple(pos)in seen
                        or not isinstance(row.get('state'),str)
                        or any(type(row.get(k))is not bool for k in ('solid','fluid','block_entity','passable'))):
                    raise IncompleteVolumeScan('场景分片包含重复、越界或缺失属性的方块')
                seen.add(tuple(pos))
            if time.monotonic()-started>12:
                raise IncompleteVolumeScan('分片扫描已过时，不使用旧场景规划')
        result.extend(reply['blocks'])
    if tiled:
        after=client.status()
        if ((after.get('world_session'),after.get('control_revision'))!=scope
                or time.monotonic()-started>12):
            raise IncompleteVolumeScan('完整分片扫描期间世界或控制状态已变化')
    return result
