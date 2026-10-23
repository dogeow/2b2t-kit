"""Release an idle owner without resolving or replaying unknown food delivery."""
def allowed(action, command, error, book, event, state, world, task):
    try:
        lease=state['supervision_lease'];food=book['pending_food']
        return (action=='pause' and command['action']=='feed_village_founders'
                and error['type']=='RuntimeError'
                and error['error']=='Original bread drop lacks its exact server collector receipt; do not repeat'
                and error['native_inflight'] is None and error['unconfirmed_native_request'] is None
                and book['complete'] is False and book['pending'] is None
                and book['world_session']==world and food['native_request']==error['last_request']
                and event['request_id']==error['last_request']==state['last_request']
                and event['op']=='villager_bread_drop' and event['phase']==state['phase']=='done'
                and event['world_session']==state['world_session']==world
                and event['params']['task_session']==lease['job_session']==task
                and event['params']['expected_uuid']==food['target']
                and lease['kind']=='materials' and lease['world_session']==world
                and event['health_before']==event['health_after']==state['health']==20
                and event['position_after']==state['pos'] and event['revision_after']==state['control_revision']
                and state['connected'] is True and state['manual_movement'] is False and state['screen']==''
                and state['menu']['cursor']['count']==0 and not state.get('navigating')
                and not state.get('native_material_busy') and not state.get('pending_scan')
                and isinstance(state['movement_keys'],dict) and not any(state['movement_keys'].values()))
    except(KeyError,TypeError,ValueError):return False
