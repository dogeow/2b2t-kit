"""One bounded dry natural column, opened top-down through ordinary mining."""
import json,time
from pathlib import Path
from kit_runtime.journal import write_json
from .acquisition import _scan,_safe,block_id,NATURAL,FALLING,_choose_tool
from .roof_harvest import light_supports
from .navigation import settled_state

HAZARDS=FALLING|{'minecraft:pointed_dripstone','minecraft:fire','minecraft:soul_fire','minecraft:cobweb'}

def plan(rows,x,z,bottom,top):
    if any(type(v)is not int for v in(x,z,bottom,top))or not -62<=bottom<=top<=316 or top-bottom>64:
        raise ValueError('Explicit natural column within64 vertical blocks required')
    cells={tuple(b['pos']):b for b in rows};protected=light_supports(rows)
    if any((x,y,z)in cells for y in(bottom,bottom+1)):
        raise RuntimeError('Resource entry bottom must already be two dry air cells')
    if any((x,y,z)in cells for y in(top+1,top+2)):
        raise RuntimeError('Resource entry top must leave two current air cells for the initial approach')
    result=[]
    for b in rows:
        bx,by,bz=b['pos']
        if abs(bx-x)<=1 and abs(bz-z)<=1 and bottom<=by<=top+1:
            if b.get('fluid')is not False or b.get('block_entity')is not False or block_id(b)in HAZARDS:
                raise RuntimeError('Natural column neighborhood has hazards or containers')
        if bx==x and bz==z and bottom<=by<=top:
            if block_id(b)not in NATURAL or tuple(b['pos'])in protected:
                raise RuntimeError('Natural column contains a protected or non-natural cell')
            result.append(b)
    return sorted(result,key=lambda b:-b['pos'][1])


def run(c,x,z,bottom,top,out,checkpoint):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'entry.json'
    if path.exists():raise RuntimeError('Original entry intent retained; no replay')
    def state():
        checkpoint();q=c.status();_safe(q)
        if q.get('flight')is not True:raise RuntimeError('Natural column requires current controlled Flight')
        return q
    rows=_scan(c,[x-2,bottom-1,z-2],[x+2,top+3,z+2],state);targets=plan(rows,x,z,bottom,top)
    book={'world_session':c.world,'column':[x,z],'bottom':bottom,'top':top,
          'planned_cells':[b['pos']for b in targets],'pending':None,'receipts':[],'complete':False};write_json(path,book)
    for original in targets:
        p=original['pos'];name=block_id(original)
        local=_scan(c,[x-1,p[1]-1,z-1],[x+1,p[1]+2,z+1],state)
        cell=next((b for b in local if b['pos']==p),None)
        if cell is None:raise RuntimeError('Entry changed before mining; no old target replay')
        if cell['state']!=original['state']or any(b.get('fluid')or b.get('block_entity')or block_id(b)in HAZARDS for b in local):
            raise RuntimeError('Entry material or neighboring hazards changed')
        point=[x+.5,p[1]+1.2,z+.5]
        c.checked('navigate',target=point,arrival=.2,air_only=True,seconds=60);settled_state(c,point,.4)
        suffix='shovel'if name in {'minecraft:dirt','minecraft:grass_block','minecraft:coarse_dirt','minecraft:clay'}else'pickaxe'
        tools=[r for r in state()['inventory']if r.get('slot',99)<36 and r.get('count')==1
               and r.get('item')in ('minecraft:diamond_'+suffix,'minecraft:netherite_'+suffix)
               and r.get('durability',0)>=len(targets)+33
               and not any(e.get('id')=='minecraft:silk_touch'for e in r.get('enchantments',[]))]
        if not tools:raise RuntimeError('Actual non-silk entry tool durability insufficient')
        tool=max(tools,key=lambda r:(max((e['level']for e in r.get('enchantments',[])if e['id']=='minecraft:efficiency'),default=0),r['durability']))
        _choose_tool(c,tool,state)
        book['pending']={'pos':p,'expected_state':cell['state'],'tool':tool};write_json(path,book)
        try:reply=c.checked('mine_block',pos=p,face='up',expected_state=cell['state'],seconds=20)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        if _scan(c,p,p,state):raise RuntimeError('Entry server cell is not removed; no repeated mine')
        book['receipts'].append({**book['pending'],'native_reply_id':reply['id'],'removed_verified':True})
        book['pending']=None;write_json(path,book)
        c.set_progress(done=len(book['receipts']),phase='自然入口逐格确认')
        print('ACTUAL_NATURAL_ENTRY_REMOVED',p,len(book['receipts']),len(targets),flush=True)
    remaining=_scan(c,[x,bottom,z],[x,top+2,z],state)
    if remaining:raise RuntimeError('Complete current entry column is not air')
    target=[x+.5,bottom+.2,z+.5]
    c.checked('navigate',target=target,arrival=.2,air_only=True,seconds=120);settled_state(c,target,.4)
    book.update(complete=True,actual_position=state()['pos'],inventory_credit_assumed=0);write_json(path,book)
    return book
