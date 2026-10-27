"""Exchange one carried armor item with one worn item using ordinary exact clicks."""
from pathlib import Path
from copy import deepcopy
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json


def identity(row):return {k:v for k,v in row.items()if k!='slot'}


def equip(client,slot,item,out,checkpoint,*,expected_source=None):
    allowed={5:'_helmet',6:'_chestplate',7:'_leggings',8:'_boots'}
    if slot not in allowed or not item.endswith(allowed[slot]):raise ValueError('Explicit ordinary armor slot and item required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);q=checkpoint();m=q['menu'];lease=q.get('supervision_lease')or{}
    if (m['type']!='InventoryMenu'or m['id']!=0 or m['cursor']['count']or q.get('screen')
            or q['health']!=20 or q.get('manual_movement')or q.get('guard_busy')
            or not q.get('guard_armed')or lease.get('kind')!='materials'
            or lease.get('job_session')!=client.task or lease.get('world_session')!=client.world
            or lease.get('revision')!=q['control_revision']):
        raise RuntimeError('Current healthy idle owner and empty inventory cursor required')
    matches=[r for r in m['slots'][9:45]if r['item']==item and r['count']==1
             and(expected_source is None or identity(r)==identity(expected_source))]
    if len(matches)!=1:raise RuntimeError('One exact carried armor identity required; preserve current gear')
    source=deepcopy(matches[0]);old=deepcopy(m['slots'][slot]);index=source['slot']
    if old['count']!=1:raise RuntimeError('Occupied armor exchange required; preserve empty-slot workflows')
    book={'world_session':client.world,'task_session':client.task,'armor_slot':slot,
          'source_slot':index,'original_armor':old,'borrowed_armor':source,'pending':'one_carried_armor_pickup','complete':False}
    path=out/'equipment-swap.json';write_json(path,book);session=InventorySession(client)
    q=session.click(q,index)
    q=session._wait(q,0,lambda m:not m['slots'][index]['count']and identity(m['cursor'])==identity(source),'armor_pickup',confirmations=2,fresh=True)
    checkpoint();book['pending']='one_worn_armor_exchange';write_json(path,book);q=session.click(q,slot)
    q=session._wait(q,0,lambda m:identity(m['slots'][slot])==identity(source)and identity(m['cursor'])==identity(old),'armor_exchange',confirmations=2,fresh=True)
    checkpoint();book['pending']='one_original_armor_store';write_json(path,book);q=session.click(q,index)
    q=session._wait(q,0,lambda m:not m['cursor']['count']and identity(m['slots'][slot])==identity(source)and identity(m['slots'][index])==identity(old),'original_armor_preserved',confirmations=2,fresh=True)
    book.update(complete=True,pending=None,actual_worn=q['menu']['slots'][slot],preserved_original=q['menu']['slots'][index]);write_json(path,book);return book
