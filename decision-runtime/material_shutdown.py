"""Observe the owned bounded native action before touching containers or exit hatches."""
import time


def settle_terminal_read(client, state):
    """Release only an exactly acknowledged read envelope after cancellation.

    Scan replies can finish without replacing status.id/op. A cancelled caller
    keeps native_inflight, so inspect its exact reply rather than the previous
    movement's terminal status. No resource action is replayed or credited.
    """
    from material_client import reply_observation, expected_native_revision
    from material_jobs.protocol import server_key
    pending = getattr(client, 'native_inflight', None)
    if not isinstance(pending, dict) or pending.get('op') not in {
            'snapshot', 'scan', 'scan_trees', 'projection_model', 'projection_audit', 'map_audit'}:
        return False
    lease = state.get('supervision_lease') or {}
    rid = pending.get('request_id')
    base = pending.get('base_revision')
    stop = state.get('control_stop') or {}
    if (not isinstance(rid, str) or not rid or rid != client.last
            or state.get('last_request') != rid or type(base) is not int
            or type(pending.get('request_revision')) is not int
            or type(pending.get('expected_revision')) is not int
            or type(state.get('control_revision')) is not int or type(lease.get('revision')) is not int
            or pending.get('request_revision') != base
            or pending.get('expected_revision') != expected_native_revision(pending['op'], base)
            or base != client.rev or state.get('control_revision') != base
            or state.get('connected') is not True or state.get('manual_movement') is not False
            or state.get('world_session') != client.world or pending.get('world_session') != client.world
            or pending.get('task_session') != client.task or lease.get('job_session') != client.task
            or lease.get('kind') != 'materials' or lease.get('world_session') != client.world
            or lease.get('revision') != base or lease.get('id') != client.heartbeat.id
            or pending.get('lease_id') != client.heartbeat.id
            or not pending.get('server') or server_key(pending['server']) != server_key(state.get('server'))
            or not pending.get('dimension') or pending['dimension'] != state.get('dimension')
            or state.get('pending_scan') is not None or state.get('navigating')
            or state.get('native_material_busy') or state.get('build_job', {}).get('active')
            or state.get('borer_active') or state.get('chopping')
            or stop.get('kind') in ('manual', 'emergency') and stop.get('revision') == base
            or state.get('safety_hold', {}).get('active')):
        return False
    observed, reply = reply_observation(client.root / ('reply-' + rid + '.json'))
    if (observed != 'valid' or reply.get('id') != rid
            or reply.get('phase') not in ('done', 'stopped', 'waiting', 'error')
            or reply.get('world_session') != client.world or reply.get('control_revision') != base
            or type(reply.get('time')) is not int or type(state.get('time')) is not int
            or reply['time'] > state['time']):
        return False
    from kit_runtime.journal import write_json
    write_json(client.out / ('observed-terminal-read-' + rid + '.json'), {
        'request_id': rid, 'op': pending['op'], 'world_session': client.world,
        'task_session': client.task, 'lease_id': client.heartbeat.id,
        'control_revision': base, 'reply_phase': reply['phase'],
        'reply_time': reply['time'], 'observed_at': state['time'],
        'resource_actions_replayed': False, 'goal_completion_credit': 0})
    if client.native_inflight is not pending:
        return False
    client.native_inflight = None
    return True


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
