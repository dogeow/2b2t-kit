"""Observe a settled trader menu wait; never replay its interaction."""
DETAIL='original processing menu not observed; block use is not repeated'
def observable_paid_reopen(command,error,lock,opening,event,state,flags,world,task,host_sha256=None):
 """Observe a failed nested open after a conserved, completed locking trade."""
 from collections import Counter
 from material_plan import inventory_counts
 try:
  purchase=lock['purchase'];selected=lock['selected'];uid=lock['uuid']
  if(command['action']!='merchant_lock_wanted' or lock['pending']!='reopen_after_purchase'
     or lock['locked']is not False or lock['world_session']!=world
     or command['targets'].get(selected['enchantment'])!=selected['level']
     or lock['quote']['villager_uuid']!=uid or selected['offer']not in lock['quote']['offers']
     or purchase['complete']is not True or purchase['pending']is not None
     or purchase['world_session']!=world or purchase['uuid']!=uid
     or purchase['after']!=purchase['expected_after']):return False
  expected=Counter(purchase['before']);offer=purchase['offer']
  for key in ('cost_a','cost_b'):
   row=offer[key]
   if row['count']:expected[row['item']]-=row['count']
  expected[offer['result']['item']]+=offer['result']['count']
  if(expected==Counter(purchase['before']) or any(n<0 for n in expected.values())
     or expected!=Counter(purchase['after']) or inventory_counts(state)!=expected):return False
  actor=next(v for v in flags['villagers']if v['uuid']==uid)
  # Bind the nested open to the currently witnessed server entity, not a new purchase.
  nested={'action':'merchant_open','actor':{'uuid':uid,'id':actor['entity_id']}}
  if error.get('error')in('Entity out of reach','Entity is occluded'):
   return observable_reach(nested,error,opening,event,state,flags,world,task,host_sha256)
  return observable(nested,error,opening,event,state,flags,world,task)
 except (KeyError,TypeError,ValueError,StopIteration):return False

def observable(command,error,opening,event,state,flags,world,task):
 return _observable(command,error,opening,event,state,flags,world,task,DETAIL,'waiting')

def observable_bridged(command,opening,event,reply,state,flags,world,task):
 """Observe an external opening's terminal wait on the same still-sleeping adult."""
 try:
  p=command['params'];uid=p['expected_uuid'];target=next(v for v in flags['villagers']if v['uuid']==uid);menu=state['menu']
  return(command['action']=='native'and command['op']=='interact_entity'
   and opening['uuid']==uid and opening['world_session']==world and opening['pending']is True
   and opening['request_id']==event['request_id']==reply['id']==state['last_request']
   and event['op']=='interact_entity'and event['phase']==reply['phase']=='waiting'
   and event['detail']==reply['detail']==DETAIL
   and event['world_session']==reply['world_session']==state['world_session']==world
   and event['params']['task_session']==task and all(event['params'].get(k)==v for k,v in p.items())
   and p['entity_id']==target['entity_id']and type(target['sleeping'])is bool and target['is_baby']is False
   and target['client_health']==20 and target['passenger']is False
   and event['inventory_delta']=={}and event['position_before']==event['position_after']==state['pos']
   and event['revision_before']==event['revision_after']==state['control_revision']
   and event['health_before']==event['health_after']==state['health']==20
   and not reply.get('outcome_pending')and state['screen']==''and menu['type']=='InventoryMenu'and menu['id']==0
   and menu['cursor']['count']==0 and state['manual_movement']is False
   and not any(state.get(k)for k in('navigating','native_material_busy','pending_scan'))
   and not any(state['movement_keys'].values()))
 except(KeyError,TypeError,ValueError,StopIteration):return False

# This host rejects both range checks before opening tracking, rotation or the
# ordinary entity interaction. A different host needs its own code audit.
REACH_HOST_SHA256='ebce50979ba7aaadc8c855e548af54169bf8dc45de86a3ff49756b9dea06dbeb'
# 20.4 bytecode audited: both range exceptions precede opening tracking,
# camera rotation and MultiPlayerGameMode.interact (host20.4-merchant-reach-bytecode-1651.txt).
REACH_HOST_SHA256S=frozenset((REACH_HOST_SHA256,'7d29812c22ed57cd52ab0e1e310e029693eca2915a652cdb8b09b1b3acbc8607'))
OCCLUSION_HOST_SHA256='7d29812c22ed57cd52ab0e1e310e029693eca2915a652cdb8b09b1b3acbc8607'
def observable_reach(command,error,opening,event,state,flags,world,task,host_sha256):
 # Current 20.4 bytecode 17641-17653 throws before opening, rotation or interaction.
 # The older host has only the prior range audit, so retain its occlusion errors.
 detail=error.get('error')
 audited=(detail=='Entity out of reach'and host_sha256 in REACH_HOST_SHA256S
          or detail=='Entity is occluded'and host_sha256==OCCLUSION_HOST_SHA256)
 return(audited and _observable(command,error,opening,event,state,flags,world,task,detail,'error'))

def _observable(command,error,opening,event,state,flags,world,task,detail,phase):
 try:
  uid=command['actor']['uuid'];target=next(v for v in flags['villagers']if v['uuid']==uid);menu=state['menu']
  return(command['action']=='merchant_open'and error['error']==detail and error['native_inflight']is None and error['unconfirmed_native_request']is None
   and opening['uuid']==uid and opening['world_session']==world and opening['pending']is True
   and opening['request_id']==error['last_request']==event['request_id']==state['last_request']
   and event['op']=='interact_entity'and event['phase']==phase and event['detail']==detail and event['world_session']==world
   and event['params']['task_session']==task and event['params']['expected_uuid']==uid and event['params']['entity_id']==command['actor']['id']
   and event['params']['expected_hand']=='minecraft:netherite_sword'and state['hand']['item']=='minecraft:netherite_sword'
   and event['inventory_delta']=={}and event['position_before']==event['position_after']==state['pos']
   and event['revision_before']==event['revision_after']==state['control_revision']and event['health_before']==event['health_after']==state['health']==20
   and type(target['sleeping'])is bool and target['client_health']==20 and target['is_baby']is False and target['passenger']is False
   and state['screen']==''and menu['type']=='InventoryMenu'and menu['id']==0 and menu['cursor']['count']==0
   and state['manual_movement']is False and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan')
   and isinstance(state['movement_keys'],dict)and not any(state['movement_keys'].values()))
 except (KeyError,TypeError,ValueError,StopIteration):return False
