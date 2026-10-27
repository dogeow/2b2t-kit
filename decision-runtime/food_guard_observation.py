"""Identify the pinned host's pre-Q refusal; this only authorizes observation."""
from material_plan import inventory_counts
HOST_SHA256='ebce50979ba7aaadc8c855e548af54169bf8dc45de86a3ff49756b9dea06dbeb'
APPROVED_HOSTS=frozenset((HOST_SHA256,'7d29812c22ed57cd52ab0e1e310e029693eca2915a652cdb8b09b1b3acbc8607'))
DETAIL='One bread drop needs the same healthy adult within three blocks and the exact held bread stack'
def confirmed_progress(feeding,events,world,task):
 try:
  totals={u:0 for u in feeding['required']};seen=set()
  for receipt in feeding['receipts']:
   rid=receipt['native_request'];packet=receipt['server_receipt'];collector=packet['collector'];actual=receipt['actual_collector'];prior=next(e for e in events if e.get('request_id')==rid);source=packet.get('joined_source',packet.get('source',{}))
   if(rid in seen or actual not in totals or collector['uuid']!=actual or collector['type']!='minecraft:villager'
      or collector.get('is_baby')is not False or collector.get('client_health')!=20
      or packet['amount']!=1 or packet['source_entity_id']!=source['id']or packet['collector_entity_id']!=collector['entity_id']
      or prior.get('world_session')!=world or prior.get('op')!='villager_bread_drop'or prior.get('phase')!='done'
      or prior.get('params',{}).get('task_session')!=task or prior['params'].get('expected_uuid')!=receipt['target']
      or prior.get('inventory_delta')!={'minecraft:bread':-1}or prior.get('health_before')!=20 or prior.get('health_after')!=20):return False
   if packet['kind']=='item_pickup':
    if packet.get('item')!='minecraft:bread':return False
   elif packet['kind']=='pickup_entities_unresolved':
    if packet.get('source_join')!='fresh_same_world_generation_item_id_uuid'or source.get('stack',{}).get('item')!='minecraft:bread'or source['stack'].get('count')!=1:return False
   else:return False
   seen.add(rid);totals[actual]+=1
  return totals==feeding['delivered']and all(0<=n<=feeding['required'][u]for u,n in totals.items())
 except(KeyError,TypeError,ValueError,StopIteration):return False

def rejected_without_q(command,error,feeding,event,state,world,task,host_hash,*,prior_events=()):
 try:
  pending=feeding['pending'];food=feeding['pending_food'];params=pending['params'];count=params['expected_count'];target=params['expected_uuid']
  return (host_hash in APPROVED_HOSTS and command['action']=='feed_village_founders'
   and error['error']==DETAIL and error['native_inflight']is None and error['unconfirmed_native_request']is None
   and feeding['world_session']==world and not feeding['complete']and confirmed_progress(feeding,prior_events,world,task)
   and pending['op']=='villager_bread_drop'and food['target']==target and not food.get('native_request')
   and type(count)is int and count>0 and food['before_bread']==count==inventory_counts(state)['minecraft:bread']
   and state['hand']['item']=='minecraft:bread'and state['hand']['count']==count
   and target in command['quotas']and command['quotas']==feeding['required']
   and event['request_id']==error['last_request']==state['last_request']and event['world_session']==world
   and event['op']=='villager_bread_drop'and event['phase']=='error'and event['detail']==DETAIL
   and event['params']['task_session']==task and all(event['params'].get(k)==v for k,v in params.items())
   and event['position_before']==event['position_after']==state['pos']and event['inventory_delta']=={}
   and event['revision_before']==event['revision_after']==state['control_revision']
   and event['health_before']==event['health_after']==state['health']==20
   and state['screen']==''and state['manual_movement']is False and not state.get('navigating')
   and not state.get('native_material_busy')and not state.get('pending_scan')and isinstance(state['movement_keys'],dict)and not any(state['movement_keys'].values()))
 except (KeyError,TypeError,ValueError):return False
