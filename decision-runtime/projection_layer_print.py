"""Print flat layers from explicit server observations using Litematica Printer.

One material owner; fixed feet height; native collision-aware travel; normal
printer interactions; no restart or retry of an unconfirmed printer interval.
"""
import math,time
from pathlib import Path
from collections import Counter
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_jobs.protocol import JobBlocked


def layer_state(expected,reply):
    if (reply.get('phase')!='done' or type(reply.get('scan_cells_read'))is not int
            or reply.get('scan_cells_read')!=reply.get('scan_total_cells')
            or reply.get('scan_start_revision')!=reply.get('scan_end_revision')):
        raise JobBlocked('当前层扫描未完整确认')
    actual={}
    for row in reply.get('blocks',[]):
        p=tuple(row['pos'])
        if p not in expected:continue
        if (p in actual or row.get('state')!='Block{minecraft:cobblestone}'
                or row.get('fluid')is not False or row.get('block_entity')is not False):
            raise JobBlocked('当前层已有方块与登记的干燥圆石不符')
        actual[p]=row['state']
    return actual


def next_window(expected,actual,position,limit=6):
    if not expected or any(type(v)is not tuple or len(v)!=3 for v in expected):raise ValueError('Explicit layer positions required')
    if len({p[1]for p in expected})!=1 or not actual.keys()<=expected:raise ValueError('One registered horizontal layer required')
    if type(limit)is not int or not 1<=limit<=8:raise ValueError('Printer window1..8 required')
    missing=expected-actual.keys()
    if not missing:return None
    if not actual:raise JobBlocked('当前层尚无已确认永久角点')
    choices=[]
    for p in actual:
        # 2.8 horizontal leaves normal ray/eye-height margin inside4.15 reach.
        mask=sorted((q for q in missing if (p[0]-q[0])**2+(p[2]-q[2])**2<=2.8**2),key=lambda q:((q[0]-p[0])**2+(q[2]-p[2])**2,q))[:limit]
        if mask:
            stand=[p[0]+.5,p[1]+1.1,p[2]+.5]
            choices.append((-len(mask),math.dist(position,stand),stand,mask))
    if not choices:raise JobBlocked('当前层没有接近缺口的已确认落脚位')
    _,_,stand,mask=min(choices)
    return {'stand':stand,'positions':[list(p)for p in mask]}


def run(client,cells,out,checkpoint):
    from material_jobs.local_air_path import move
    from material_jobs.navigation import settled_state
    from material_jobs.acquisition import _safe
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    points={tuple(p)for p in cells}
    if (len(points)!=len(cells) or not 1<=len(points)<=2048
            or len({p[1]for p in points})>16 or any(any(type(n)is not int for n in p)for p in points)):
        raise ValueError('Bounded exact registered layer cells required')
    q=checkpoint();world=client.world;key=q['projection_selection']['key'];book={'world_session':world,'placement_key':key,'complete':False,'pending':None,'windows':[]}
    def save():write_json(out/'progress.json',book)
    def state():
        checkpoint();s=client.status();_safe(s)
        if (s.get('world_session')!=world or s.get('projection_selection',{}).get('key')!=key
                or s.get('health',0)<19 or s.get('screen') or s.get('manual_movement')
                or not s.get('flight') or s.get('air_place') or s.get('build_job',{}).get('active')):
            raise JobBlocked('固定层打印的健康、飞行或投影状态变化')
        return s
    save()
    for y in sorted({p[1]for p in points},reverse=True):
        expected={p for p in points if p[1]==y};low=[min(p[0]for p in expected),y,min(p[2]for p in expected)];high=[max(p[0]for p in expected),y,max(p[2]for p in expected)]
        def scan():
            state();r=client.request('scan',min=low,max=high,details=True)
            if r.get('world_session')!=world:raise JobBlocked('当前层扫描世界变化')
            return layer_state(expected,r)
        actual=scan()
        while len(actual)<len(expected):
            s=state();plan=next_window(expected,actual,s['pos']);index=len(book['windows']);d=out/f'window-{index:03}';d.mkdir()
            move(client,plan['stand'],d/'approach',foot_offset=.1,max_horizontal=24,exact_target=True)
            settled_state(client,plan['stand'],.4);state();client.checked('select_item',item='minecraft:cobblestone')
            before=inventory_counts(state()).get('minecraft:cobblestone',0)
            client.checked('projection_batch_set',placement_key=key,positions=plan['positions'],min_feet_y=y+1)
            entry={'layer':y,'plan':plan,'inventory_before':before,'pending':True};book['windows'].append(entry);book['pending']='professional_print';save()
            try:r=client.request('professional_print',seconds=15)
            finally:entry['request_id']=client.last;save()
            write_json(d/'printer-receipt.json',r)
            if r.get('phase')!='done':raise JobBlocked('当前打印窗口未完整确认；保留原回执，不重放')
            after=scan();new=after.keys()-actual.keys();mask={tuple(p)for p in plan['positions']}
            if new!=mask or inventory_counts(state()).get('minecraft:cobblestone',0)!=before-len(new):
                raise JobBlocked('打印窗口的实际方块或物资变化不匹配；保留现场')
            client.checked('projection_batch_clear',placement_key=key)
            entry.update(pending=False,placed=len(new));book['pending']=None;book['matched']=sum(p[1]>y for p in points)+len(after);save();actual=after
            print('LAYER_PRINT',y,len(actual),len(expected),flush=True)
    book['complete']=True;book['matched']=len(points);save();return book
