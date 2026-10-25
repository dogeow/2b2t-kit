"""Read-only settlement of native fixed-tree validation's own two-revision stop."""
DETAIL='Fixed tree is absent, ambiguous, unloaded or outside its bounds'

def observable(command,reply,event,state,world,task):
    params=command.get('params')or{};ep=event.get('params')or{};lease=state.get('supervision_lease')or{}
    before=event.get('revision_before');after=event.get('revision_after')
    return (command.get('action')=='native'and command.get('op')=='chop'
        and all(isinstance(params.get(k),list)and len(params[k])==3 and all(type(n)is int for n in params[k])for k in ('tree_root','tree_min','tree_max'))
        and all(ep.get(k)==params[k]for k in ('tree_root','tree_min','tree_max','item','tree_limit'))
        and reply.get('phase')=='stopped'and reply.get('detail')=='脚本参数无效'
        and state.get('phase')=='error'and state.get('detail')==DETAIL
        and event.get('op')=='chop'and event.get('phase')==reply['phase']and event.get('detail')==reply['detail']
        and event.get('world_session')==reply.get('world_session')==state.get('world_session')==world
        and event.get('request_id')==reply.get('id')==state.get('last_request')
        and ep.get('task_session')==lease.get('job_session')==task and lease.get('world_session')==world and lease.get('kind')=='materials'
        and type(before)is int and type(after)is int and after-before==2
        and after==state.get('control_revision')==reply.get('control_revision')==lease.get('revision')
        and isinstance(event.get('position_before'),list)and len(event['position_before'])==3
        and event['position_before']==event.get('position_after')==state.get('pos')and event.get('inventory_delta')=={}
        and state.get('health')==20 and state.get('connected')is True and state.get('manual_movement')is False and not state.get('screen')
        and not any(state.get(k)for k in ('chopping','chopper_remaining','chopper_platforms','navigating','pending_scan','native_material_busy','guard_busy')))
