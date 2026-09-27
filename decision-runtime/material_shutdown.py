"""Observe the owned bounded native action before touching containers or exit hatches."""
import time


def drain_pending(client,seconds=140):
    deadline=time.monotonic()+seconds;waiting=False
    while True:
        try:state=client.raw()
        except (OSError,RuntimeError,ValueError) as error:
            return {'safe_to_cleanup':False,'reason':'observation_unavailable','error':str(error)}
        lease=state.get('supervision_lease') or {}
        owned=(state.get('connected') and state.get('world_session')==client.world
               and not state.get('manual_movement') and client.last is not None and state.get('last_request')==client.last
               and lease.get('kind')=='materials' and lease.get('job_session')==client.task
               and lease.get('revision')==state.get('control_revision'))
        if not owned:return {'safe_to_cleanup':False,'reason':'control_handoff','state':state}
        if state.get('phase') in ('done','waiting','stopped','error'):
            if waiting and state.get('health',0)<14:return {'safe_to_cleanup':False,'reason':'low_health','state':state}
            client.rev=state['control_revision']
            return {'safe_to_cleanup':True,'reason':'owned_action_settled','state':state}
        if state.get('phase')!='running':return {'safe_to_cleanup':False,'reason':'unknown_action_phase','state':state}
        if state.get('health',0)<14:return {'safe_to_cleanup':False,'reason':'low_health','state':state}
        if time.monotonic()>=deadline:return {'safe_to_cleanup':False,'reason':'pending_action_timeout','state':state}
        waiting=True;time.sleep(.15)
