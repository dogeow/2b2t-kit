"""A fully accounted food budget can be observed even when recipients differ."""
from collections import Counter
from material_plan import inventory_counts

def accounted_budget(command,result,events,state,world,task):
 try:
  required=command['quotas'];rows=result['receipts'];native={e['request_id']:e for e in events};seen=set();counts=Counter();requests=set();last=None
  if(command['action']!='feed_village_founders'or result['world_session']!=world or result['required']!=required
     or result['complete']is not False or result['pending']is not None or result['pending_food']is not None
     or result.get('recovery_pending')is not None or len(rows)!=sum(required.values())or not rows):return False
  for row in rows:
   packet=row['server_receipt'];uid=packet['collector']['uuid'];source=packet.get('source')if packet['kind']=='item_pickup'else packet.get('joined_source')if packet.get('source_join')=='fresh_same_world_generation_item_id_uuid'else None
   if(not source or source['type']!='minecraft:item'or not source.get('uuid')or source['uuid']in seen
      or packet['amount']!=1 or packet['collector']['type']!='minecraft:villager'or uid!=row['actual_collector']
      or len(set(row['debit_times']))<2 or row['native_request']in requests):return False
   if packet['kind']=='item_pickup':
    if packet['item']!='minecraft:bread':return False
   elif source['id']!=packet['source_entity_id']or source['stack']['item']!='minecraft:bread'or source['stack']['count']!=1:return False
   e=native[row['native_request']]
   if(e['world_session']!=world or e['params']['task_session']!=task or e['params']['expected_uuid']!=row['target']
      or e['op']!='villager_bread_drop'or e['phase']!='done'or e['inventory_delta']!={'minecraft:bread':-1}
      or e['health_before']!=20 or e['health_after']!=20):return False
   seen.add(source['uuid']);requests.add(row['native_request']);counts[uid]+=1;last=e
  if result['delivered']!={u:counts[u]for u in required}or result.get('other_villager_deliveries',{})!={u:n for u,n in counts.items()if u not in required}:return False
  return (result['remaining']=={u:max(0,n-counts[u])for u,n in required.items()}and result['bread_actual']==inventory_counts(state)['minecraft:bread']
   and state['last_request']==last['request_id']and state['control_revision']==last['revision_after']and state['health']==20
   and state['screen']==''and state['manual_movement']is False and not state.get('navigating')and not state.get('native_material_busy')
   and not state.get('pending_scan')and isinstance(state['movement_keys'],dict)and not any(state['movement_keys'].values()))
 except (KeyError,TypeError,ValueError):return False
