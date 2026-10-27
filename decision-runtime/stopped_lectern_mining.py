"""Read an acknowledged mining abort; never replay or credit it."""
from material_plan import inventory_counts
DETAIL='Lectern reset requires an empty lectern beside the same freshly quoted untraded librarian without a requested book'

def preview(command,reply,event,state,world,task,*,allow_unacknowledged_readback=False):
 p=command.get('params')or{};n=reply.get('native_sequence')
 acknowledged=reply.get('server_ack_sequence')==n
 pending_ack=(allow_unacknowledged_readback is True and reply.get('server_ack_sequence')==-1
              and reply.get('outcome_pending')is True)
 if(command.get('action')!='native'or command.get('op')!='mine_block'
    or p.get('reset_empty_lectern')is not True or not all(p.get(k)for k in ('expected_villager_uuid','expected_quote_opening','expected_offers_fingerprint'))
    or not str(p.get('expected_state','')).startswith('Block{minecraft:lectern}')or 'has_book=false'not in p['expected_state']
    or reply.get('phase')!='waiting'or reply.get('detail')!=DETAIL
    or type(n)is not int or n<=0 or not(acknowledged or pending_ack)
    or reply.get('server_confirmed')is not False or reply.get('mining_target')!=p.get('pos')
    or reply.get('world_session')!=world or reply.get('id')!=state.get('last_request')
    or not event or event.get('request_id')!=reply.get('id')or event.get('op')!='mine_block'
    or event.get('phase')!='waiting'or event.get('detail')!=DETAIL or event.get('world_session')!=world
    or event.get('inventory_delta')!={}or event.get('params',{}).get('task_session')!=task
    or any(event.get('params',{}).get(k)!=v for k,v in p.items())
    or type(event.get('revision_before'))is not int or event.get('revision_after')!=event['revision_before']+1
    or event.get('revision_after')!=state.get('control_revision')
    or event.get('position_before')!=event.get('position_after')or event.get('position_after')!=state.get('pos')
    or reply.get('pos')!=state.get('pos')or event.get('health_before')!=20 or event.get('health_after')!=20
    or inventory_counts(reply)!=inventory_counts(state)or state.get('world_session')!=world
    or state.get('health')!=20 or state.get('manual_movement')is not False or state.get('screen')!=''
    or any(state.get(k)for k in ('navigating','native_material_busy','pending_scan','material_mining_cleanup_pending'))):
  raise ValueError('No conserved acknowledged lectern abort')
 return dict(pending=True,world_session=world,task_session=task,original_command=command,
             original_reply=reply,original_event=event,target=p['pos'],expected_state=p['expected_state'],
             inventory=dict(inventory_counts(state)),pos=state['pos'],mining_credit=0,replayed=False,
             acknowledgement_pending=not acknowledged,native_claim_not_cleared=True)

def read_allowed(marker,action,params):
 p=params.get('params')or{}
 return (action=='native'and params.get('op')=='scan'and p.get('include_predictions')is True
         and p.get('min')==p.get('max')==marker['target']and p.get('details')is True)

def reconcile(marker,frames,states):
 if len(frames)!=2 or len(states)!=2 or not states[0]['time']<states[1]['time']:
  raise ValueError('Two fresh observations required')
 for f,s in zip(frames,states):
  pred=f.get('scan_predictions')or{};rows={tuple(r['pos']):r for r in f.get('blocks',[])}
  if(f.get('world_session')!=marker['world_session']or f.get('scan_cells_read')!=1 or f.get('scan_total_cells')!=1
     or pred.get('complete')is not True or pred.get('pending_count')!=0 or pred.get('pending_positions')!=[]
     or rows.get(tuple(marker['target']),{}).get('state')!=marker['expected_state']
     or s.get('world_session')!=marker['world_session']or s.get('health')!=20
     or s.get('manual_movement')is not False or s.get('screen')!=''or s.get('pos')!=marker['pos']
     or dict(inventory_counts(s))!=marker['inventory']):
   raise ValueError('Target or stock not proved unchanged; retain the original fence')
 classification=('unacknowledged_stop_target_currently_unchanged_outcome_unresolved'
                 if marker.get('acknowledgement_pending') else 'acknowledged_abort_target_and_inventory_unchanged')
 return dict(marker,pending=False,classification=classification,
             original_outcome_unresolved=bool(marker.get('acknowledgement_pending')),
             frames=frames,observed_times=[s['time']for s in states])
