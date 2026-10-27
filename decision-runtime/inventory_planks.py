"""One carried log to four planks through the ordinary 2x2 inventory grid."""
import time
from pathlib import Path
from material_plan import inventory_counts
from kit_runtime.journal import write_json


def craft_one(q, checkpoint, proof):
    path=Path(proof)
    if path.exists():raise RuntimeError('Retain the original inventory craft; never replay it')
    state=checkpoint();menu=state.get('menu')or{}
    if(menu.get('type')!='InventoryMenu'or menu.get('id')!=0 or menu.get('cursor',{}).get('count')
            or len(menu.get('slots',[]))!=46 or any(menu['slots'][i].get('count')for i in range(5))):
        raise RuntimeError('Empty ordinary inventory crafting grid and cursor required')
    source=next((v for v in menu['slots'][9:45]if v.get('item')=='minecraft:dark_oak_log'and v.get('count',0)>0),None)
    if not source:raise RuntimeError('One actual carried dark oak log required')
    if not any(not v['count']or v['item']=='minecraft:dark_oak_planks'and v['count']<=60 for v in menu['slots'][9:45]):
        raise RuntimeError('Four planks need verified inventory capacity')
    before=inventory_counts(state);book={'complete':False,'pending':None,'world_session':q.world,
                                      'inventory_before':dict(before),'steps':[]};write_json(path,book)
    def click(slot,button=0,kind='pickup'):
        s=checkpoint();m=s['menu'];cell=m['slots'][slot];cursor=m['cursor']
        params={'menu_id':0,'slot':slot,'expected_item':cell['item'],'expected_count':cell['count'],
                'expected_cursor':cursor['item'],'expected_cursor_count':cursor['count'],'button':button,'kind':kind}
        book['pending']={'op':'slot_click','params':params};write_json(path,book)
        r=q.native('slot_click',**params);book['pending']=None;book['steps'].append({'slot':slot,'request':r.get('id')});write_json(path,book)
    def observed(test):
        deadline=time.monotonic()+6;times=[]
        while len(times)<2:
            s=checkpoint()
            if test(s):
                if not times or times[-1]!=s['time']:times.append(s['time'])
            else:times=[]
            if time.monotonic()>deadline:raise RuntimeError('Original inventory click lacks conserved later state; no replay')
            time.sleep(.1)
        return s
    slot=source['slot'];n=source['count'];click(slot)
    observed(lambda s:s['menu']['cursor']['item']=='minecraft:dark_oak_log'and s['menu']['cursor']['count']==n
             and s['menu']['slots'][slot]['count']==0)
    click(1,button=1)
    observed(lambda s:s['menu']['slots'][1]['item']=='minecraft:dark_oak_log'and s['menu']['slots'][1]['count']==1
             and s['menu']['cursor']['count']==n-1)
    if n>1:
        click(slot);observed(lambda s:s['menu']['cursor']['count']==0 and s['menu']['slots'][slot]['count']==n-1)
    observed(lambda s:s['menu']['slots'][0]['item']=='minecraft:dark_oak_planks'and s['menu']['slots'][0]['count']==4)
    click(0,kind='quick_move');expected=before.copy();expected['minecraft:dark_oak_log']-=1;expected['minecraft:dark_oak_planks']+=4
    final=observed(lambda s:inventory_counts(s)==+expected and not s['menu']['cursor']['count']
                   and all(not s['menu']['slots'][i]['count']for i in range(5)))
    book.update(complete=True,pending=None,inventory_after=dict(inventory_counts(final)),consumed_logs=1,produced_planks=4)
    write_json(path,book);return book
