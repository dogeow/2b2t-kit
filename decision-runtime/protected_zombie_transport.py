"""Only exact named or engine-bound farm bait may use the shared route kernel."""
import json,time
from pathlib import Path
from capture_target import acknowledgement,BAIT_TYPES

def aboard(vehicle,expected,state,request,ack):
    lease=state.get('supervision_lease')or{}
    passengers=vehicle.get('passengers')or[]
    return (len(expected)==1 and len(passengers)==1
        and request.get('expected_type')in BAIT_TYPES
        and request.get('entity_uuid')==expected[0]
        and request.get('world_session')==state.get('world_session')==lease.get('world_session')
        and request.get('lease_id')==lease.get('id') and bool(lease.get('id'))
        and request.get('task_session')==lease.get('job_session') and bool(lease.get('job_session'))
        and lease.get('kind')=='materials'
        and request.get('player_uuid')==state.get('player_uuid')
        and type(request.get('control_revision'))is int
        and request['control_revision']<=state.get('control_revision',-1)
        and state.get('connected')is True and state.get('manual_movement')is False
        and not state.get('screen') and state.get('health')==20
        and not state.get('safety_hold',{}).get('active') and not state.get('health_recovery_hold')
        and ack is not None and ack.get('active')is True
        and ack.get('id')==request.get('id') and ack.get('entity_uuid')==expected[0]
        and passengers[0].get('uuid')==expected[0]
        and passengers[0].get('type')==request['expected_type']
        and passengers[0].get('alive')is True and passengers[0].get('health')==20
        and (ack.get('named')is True and passengers[0].get('has_custom_name')is True
             or ack.get('boat_bound')is True and ack.get('runtime_version')in('1.8.21','1.8.22','1.8.23','1.8.24','1.8.25','1.8.26','1.8.27','1.8.28')
                and bool(request.get('boat_uuid'))and request['boat_uuid']==ack.get('boat_uuid')==vehicle.get('uuid')
                and passengers[0].get('has_custom_name')is False)
        and vehicle.get('leashed')is True and vehicle.get('leash_resolved')is True
        and vehicle.get('leash_holder',{}).get('uuid')==state.get('player_uuid'))

def observed_aboard(root,vehicle,expected,state):
    try:request=json.loads((Path(root)/'capture-target.json').read_text())
    except(OSError,ValueError):return False
    # The protection publisher can advance between two host status frames.
    # Its age must use the current clock, rather than an older status timestamp.
    ack=acknowledgement(root,request,int(time.time()*1000))
    return aboard(vehicle,expected,state,request,ack)
