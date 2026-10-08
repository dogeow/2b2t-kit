"""Permit a fresh tree audit after a known deadline stop; never promote STOPPED to DONE."""

def allow_deadline_goal_audit(reply, terminal, current, *, world, task, lease_id,
                             revision, inventory_before, expected_logs, dirt_before,
                             unknown=None, native_inflight=None):
    if unknown is not None or native_inflight is not None:
        return False
    lease=current.get('supervision_lease') or {}
    if not (reply.get('phase')=='stopped' and reply.get('detail')=='脚本任务达到时间上限'
            and terminal.get('op')=='chop' and terminal.get('phase')=='stopped'
            and reply.get('id')==terminal.get('request_id')==current.get('last_request')
            and reply.get('world_session')==terminal.get('world_session')==current.get('world_session')==world
            and terminal.get('task_session')==task and current.get('control_revision')==revision
            and terminal.get('revision_after')==revision and reply.get('control_revision')==revision
            and lease.get('kind')=='materials' and lease.get('id')==lease_id
            and lease.get('job_session')==task and lease.get('world_session')==world and lease.get('revision')==revision
            and current.get('connected') is True and current.get('health')==20 and current.get('food',0)>=18
            and current.get('guard_armed') is True and current.get('guard_pve_only') is True
            and current.get('screen')=='' and current.get('manual_movement') is False
            and not current.get('guard_busy') and not (current.get('safety_hold')or{}).get('active')
            and current.get('chopping') is False and current.get('navigating') is False
            and not current.get('native_material_busy') and current.get('pending_scan') is None
            and reply.get('chopper_verified_trees')==current.get('chopper_verified_trees')==1
            and current.get('chopper_platforms')==0
            and type(current.get('time')) is int and type(reply.get('time')) is int
            and current['time']>=reply['time']
            and type(expected_logs) is int and 1<=expected_logs<=64):
        return False
    rows=current.get('inventory')
    if not isinstance(rows,list) or len(rows)!=43 or {row.get('slot')for row in rows}!=set(range(43)):
        return False
    if any(type(row.get('count'))is not int or row['count']<0 for row in rows):
        return False
    count=lambda item:sum(row['count']for row in rows if row.get('item')==item)
    return count('minecraft:cherry_log')==inventory_before+expected_logs and count('minecraft:dirt')==dirt_before
