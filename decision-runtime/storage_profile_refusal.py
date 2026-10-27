"""Read-only settlement of an exchange refused before its storage adapter runs."""

def observable(command,error,event,state,world,task):
    lease=state.get('supervision_lease')or{}
    return bool(command.get('action')in('exchange','audit_depots')and command.get('profile')
        and ((error.get('type')=='RuntimeError'
              and error.get('error')=='Original registered storage profile changed during its live route')
             or (error.get('type')=='JobBlocked'
                 and error.get('error')=='Storage position has no current scoped Kit record'
                 and isinstance(command.get('positions'),list)and len(command['positions'])==1))
        and error.get('native_inflight')is None and error.get('unconfirmed_native_request')is None
        and isinstance(event,dict)and event.get('request_id')==error.get('last_request')==state.get('last_request')
        and event.get('phase')=='done' and event.get('world_session')==world
        and (event.get('params')or{}).get('task_session')==task
        and event.get('revision_after')==state.get('control_revision')
        and state.get('connected')is True and state.get('world_session')==world
        and state.get('health')==20 and state.get('manual_movement')is False
        and state.get('screen')==''and not state.get('guard_busy')
        and not(state.get('safety_hold')or{}).get('active')
        and lease.get('kind')=='materials'and lease.get('world_session')==world
        and lease.get('job_session')==task and lease.get('revision')==state.get('control_revision'))
