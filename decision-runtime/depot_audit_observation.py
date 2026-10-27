"""Recognize a read-only depot audit stopped by an absent scoped record."""
from collections import Counter
from material_plan import inventory_counts

def observable(command,error,partial,prior,state,event,world,task):
    try:
        positions=command['positions'];items=command['items'];visited=partial['visited']
        if (command['action']!='audit_depots' or not positions or len({tuple(p) for p in positions})!=len(positions)
                or not items or len(set(items))!=len(items)
                or error['error']!='Storage position has no current scoped Kit record'
                or error['type']!='JobBlocked'
                or error['native_inflight']is not None or error['unconfirmed_native_request']is not None
                or partial['complete']is not False or partial['world_session']!=world
                or len(visited)>=len(positions) or [v['pos']for v in visited]!=positions[:len(visited)]
                or set(partial['counts'])!=set(items)):return False
        total=Counter()
        for row in visited:
            if (set(row['counts'])!=set(items) or not prior['time']<=row['at_ms']<=state['time']
                    or any(type(n)is not int or n<0 for n in row['counts'].values())):return False
            total.update(row['counts'])
        if any(partial['counts'][item]!=total[item]for item in items):return False
        return (prior['world_session']==state['world_session']==event['world_session']==world
                and prior['phase']=='done' and event['phase']==state['phase']=='done'
                and event['request_id']==error['last_request']==state['last_request']
                and event['op']in ('navigate','walk','scan','snapshot','close_menu')
                and event['params']['task_session']==task
                and event['revision_after']==state['control_revision']
                and event['position_after']==state['pos']
                and event['inventory_delta']=={} and inventory_counts(prior)==inventory_counts(state)
                and event['health_before']==event['health_after']==state['health']==20
                and state['screen']=='' and not state.get('navigating')
                and not state.get('native_material_busy') and not state.get('pending_scan')
                and isinstance(state.get('movement_keys'),dict)and not any(state['movement_keys'].values()))
    except (KeyError,TypeError,ValueError):return False
