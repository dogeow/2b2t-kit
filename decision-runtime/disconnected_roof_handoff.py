"""Admit only a new-world snapshot owner; preserve the old unknown roof input.

This does not resolve the old mining receipt. The old target must remain
fenced, including under the new connection, while unrelated work resumes.
"""
from material_plan import inventory_counts

STATE='Block{minecraft:dark_oak_planks}'

def _disconnected_error(unknown,error,observation,current):
 if error.get('error')=='World disconnected':return True
 if error.get('error')!='Control revision changed outside the owned request':return False
 safety=current.get('supervision_safety')or{}
 reply=observation.get('original_native_reply')or{}
 return (bool(unknown.get('lease_id')) and bool(unknown.get('task_session'))
         and safety.get('lease')==unknown['lease_id']
         and safety.get('job_session')==unknown['task_session']
         and safety.get('cause')=='heartbeat_lost' and safety.get('action')=='LOGOUT'
         and safety.get('confirmed')is True and safety.get('confirmation')=='network_disconnect_event'
         and type(safety.get('confirmed_at'))is int and safety['confirmed_at']<=current.get('time',0)
         and reply.get('id')==unknown.get('request_id')
         and reply.get('world_session')==unknown.get('world_session')
         and reply.get('phase')=='stopped' and reply.get('server_confirmed')is False
         and type(reply.get('native_sequence'))is int and reply['native_sequence']>0
         and reply.get('server_ack_sequence')==-1)

def admit(unknown,error,observation,current,start):
 p=unknown.get('params')or{};pos=p.get('pos');world=current.get('world_session')
 if(unknown.get('op')!='mine_block'or p.get('expected_state')!=STATE
    or set(p)-{'pos','expected_state','seconds'}
    or not isinstance(pos,list)or len(pos)!=3 or any(type(n)is not int for n in pos)
    or not 760977<=pos[0]<=761036 or pos[1]not in (67,68)or not 797786<=pos[2]<=797818
    or not world or world==unknown.get('world_session')
    or not _disconnected_error(unknown,error,observation,current)or error.get('type')!='Handoff'
    or(error.get('native_inflight')or{}).get('request_id')!=unknown.get('request_id')
    or error.get('unconfirmed_native_request')!=unknown
    or observation.get('unknown')!=unknown or observation.get('complete')is not True
    or observation.get('old_request_replayed')is not False
    or observation.get('old_mining_completion_claimed')is not False
    or start.get('action')!='native'or start.get('op')!='snapshot'or start.get('params')!={}):
  raise ValueError('No narrow new-world read-only admission')
 baseline=observation['baseline_before_unknown'];snapshot=observation['snapshot']
 expected=set(observation.get('expected_known_uuids')or[])
 loaded=current.get('loaded_villagers',{}).get('villagers')or[]
 if(not 50<=len(expected)<=64 or len({v['uuid']for v in loaded})<45
    or any(v.get('uuid')not in expected or v.get('health')!=20 for v in loaded)
    or current.get('connected')is not True or current.get('health')!=20 or current.get('screen')!=''
    or current.get('manual_movement')is not False or current.get('supervision_lease')
    or current.get('health_recovery_hold')or(current.get('safety_hold')or{}).get('active')
    or any(current.get(k)for k in ('navigating','native_material_busy','pending_scan','material_mining_cleanup_pending'))
    or snapshot.get('world_session')!=world or baseline.get('world_session')!=unknown['world_session']
    or not baseline.get('player_uuid')or baseline.get('health')!=20
    or any(current.get(k)!=baseline.get(k)for k in ('server','dimension','player_uuid'))
    or current.get('dimension')!='minecraft:overworld'
    or inventory_counts(baseline)!=inventory_counts(snapshot)or inventory_counts(snapshot)!=inventory_counts(current)):
  raise ValueError('Current safe base identity, stock or unloaded population not bounded')
 frames=observation.get('frames')or[];states=observation.get('states')or[]
 if len(frames)!=2 or len(states)!=2 or not states[0]['time']<states[1]['time']:
  raise ValueError('Two independent roof observations required')
 if not -1000<=current['time']-states[-1]['time']<=10000:
  raise ValueError('Fresh roof observation required before startup')
 for frame,state in zip(frames,states):
  pred=frame.get('scan_predictions')or{};rows=frame.get('blocks')or[]
  if(frame.get('world_session')!=world or state.get('world_session')!=world
     or frame.get('scan_cells_read')!=1 or frame.get('scan_total_cells')!=1
     or pred.get('complete')is not True or pred.get('pending_count')!=0 or pred.get('pending_positions')!=[]
     or len(rows)!=1 or rows[0].get('pos')!=pos or rows[0].get('state')!=STATE
     or state.get('health')!=20 or state.get('screen')!=''or state.get('manual_movement')is not False
     or inventory_counts(state)!=inventory_counts(current)):
   raise ValueError('Roof or stock observations are incomplete; no new owner')
 return {'classification':'new_world_snapshot_only_old_roof_input_retained',
         'source_world':unknown['world_session'],'new_world':world,'protected_target':pos,
         'old_request_id':unknown['request_id'],'old_request_replayed':False,
         'old_mining_completion_claimed':False,'mining_credit':0,'full_population_recheck_required':True}
