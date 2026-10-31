"""Admit observation of an exact printer interval which sent no proposal."""
from material_plan import inventory_counts

def conserved(command,reply,prior_intent,prior,event,state,world,task):
 targets=reply.get('bounded_targets');key=reply.get('placement_key');mask=state.get('projection_batch')or{}
 if(not isinstance(targets,list)or not targets or len(targets)>512 or any(not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)for p in targets)):return False
 for s in (reply,state):
  p=s.get('professional_printer')or{}
  if(p.get('enabled')is not False or p.get('owned')is not False or p.get('waiting_for_server')is not False
     or any(type(p.get(k))is not int or p[k]!=0 for k in ('fast_proposals','complex_proposals','server_confirmed','travel_pending'))
     or p.get('last_proposal')!={}or p.get('failure')!=''):return False
 return(command.get('action')=='native'and command.get('op')=='professional_print'
  and reply.get('phase')=='waiting'and reply.get('detail')=='printer interval ended without complete current bounded-mask server confirmation'
  and reply.get('world_session')==state.get('world_session')==world and reply.get('id')==state.get('last_request')
  and reply.get('bounded_target_count')==len(targets)and len(set(map(tuple,targets)))==len(targets)
  and isinstance(key,str)and bool(key)and mask.get('active')is True and mask.get('count')==len(targets)
  and mask.get('placement_key')==key and mask.get('task_session')==task
  and prior_intent.get('action')=='native'and prior_intent.get('op')=='projection_batch_set'
  and prior_intent.get('params',{}).get('positions')==targets and prior_intent['params'].get('placement_key')==key
  and prior.get('phase')=='done'and prior.get('world_session')==world
  and inventory_counts(prior)==inventory_counts(reply)==inventory_counts(state)
  and bool(event)and event.get('request_id')==reply['id']and event.get('op')=='professional_print'
  and event.get('phase')=='waiting'and event.get('detail')==reply['detail']and event.get('world_session')==world
  and event.get('inventory_delta')=={}and event.get('health_before')==event.get('health_after')==state.get('health')==20
  and event.get('revision_before')==prior.get('control_revision')
  and event.get('revision_after')==reply.get('control_revision')==state.get('control_revision')
  and event.get('params',{}).get('task_session')==task
  and state.get('manual_movement')is False and state.get('screen')==''
  and not any(state.get(k)for k in ('navigating','native_material_busy','pending_scan'))
  and isinstance(state.get('movement_keys'),dict)and not any(state['movement_keys'].values()))


def terminal_unqueued(command,reply,mask_event,mask_reply,event):
 """Classify only the historical interval, never current-world state or success.

 This does not authorize replay or placement. A new correction still needs
 fresh world, owner, target and inventory checks. Legacy outcome_pending=true
 alone cannot distinguish an interval with zero queued proposals from a sent use.
 """
 world=reply.get('world_session');task=command.get('task_session');targets=reply.get('bounded_targets');key=reply.get('placement_key');p=reply.get('professional_printer')or{}
 if(not isinstance(world,str)or not world or not isinstance(task,str)or not task
    or not isinstance(targets,list)or not targets or len(targets)>512
    or any(not isinstance(v,list)or len(v)!=3 or any(type(n)is not int for n in v)for v in targets)
    or len(set(map(tuple,targets)))!=len(targets)):return False
 if(p.get('enabled')is not False or p.get('owned')is not False or p.get('waiting_for_server')is not False
    or any(type(p.get(k))is not int or p[k]!=0 for k in ('fast_proposals','complex_proposals','server_confirmed','travel_pending'))
    or p.get('last_proposal')!={}or p.get('failure')!=''):return False
 batch=reply.get('projection_batch')or{};lease=reply.get('supervision_lease')or{}
 return(command.get('id')==reply.get('id')and command.get('op')=='professional_print'and command.get('world_session')==world
   and reply.get('op')=='professional_print'and reply.get('phase')=='waiting'
   and reply.get('detail')=='printer interval ended without complete current bounded-mask server confirmation'
   and reply.get('server_confirmed')is False and reply.get('bounded_target_count')==len(targets)
   and isinstance(key,str)and bool(key)and batch.get('active')is True and batch.get('count')==len(targets)
   and batch.get('placement_key')==key and batch.get('task_session')==lease.get('job_session')==task
   and lease.get('kind')=='materials'and lease.get('world_session')==world
   and mask_event.get('op')=='projection_batch_set'and mask_event.get('phase')=='done'
   and mask_event.get('world_session')==mask_reply.get('world_session')==world
   and mask_reply.get('id')==mask_event.get('request_id')and mask_reply.get('phase')=='done'
   and mask_event.get('params',{}).get('positions')==targets and mask_event['params'].get('placement_key')==key
   and command.get('expected_revision')==mask_reply.get('control_revision')==event.get('revision_before')
   and event.get('request_id')==reply['id']and event.get('op')=='professional_print'and event.get('phase')=='waiting'
   and event.get('world_session')==world and event.get('params',{}).get('task_session')==task
   and event.get('detail')==reply['detail']and event.get('inventory_delta')=={}
   and event.get('health_before')==event.get('health_after')==reply.get('health')==20
   and event.get('revision_after')==reply.get('control_revision')
   and inventory_counts(mask_reply)==inventory_counts(reply)
   and reply.get('manual_movement')is False and reply.get('screen')==''
   and not any(reply.get(k)for k in ('navigating','native_material_busy','pending_scan'))
   and isinstance(reply.get('movement_keys'),dict)and not any(reply['movement_keys'].values()))
