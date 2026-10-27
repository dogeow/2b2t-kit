"""Recognise a single explicit negative server update, never a successful print."""
from material_plan import inventory_counts

def conserved_server_rejection(command,reply,prior_intent,prior,event,state,world,task):
    targets=reply.get('bounded_targets');key=reply.get('placement_key');printer=reply.get('professional_printer')or{};proposal=printer.get('last_proposal')or{}
    if(not isinstance(targets,list)or len(targets)!=1 or not isinstance(targets[0],list)or len(targets[0])!=3
            or any(type(v)is not int for v in targets[0])):return False
    target=', '.join(map(str,targets[0]));current=state.get('professional_printer')or{};mask=state.get('projection_batch')or{}
    return(command.get('action')=='native'and command.get('op')=='professional_print'
        and reply.get('phase')=='error'and reply.get('detail')=='服务器未确认上一格，已停止放置；请检查网络或权限'
        and reply.get('server_confirmed')is False and reply.get('outcome_pending')is True
        and reply.get('bounded_target_count')==1 and isinstance(key,str)and bool(key)
        and reply.get('world_session')==world==state.get('world_session')and reply.get('id')==state.get('last_request')
        and proposal.get('interaction_seen')is True and proposal.get('server_update_seen')is True
        and proposal.get('interaction_matches_proposal')is True and proposal.get('target')==target
        and proposal.get('server_update_state')=='Block{minecraft:air}'
        and type(proposal.get('sent_tick'))is int and type(proposal.get('server_update_tick'))is int
        and proposal['server_update_tick']>=proposal['sent_tick']>=0
        and printer.get('server_confirmed')==0 and printer.get('fast_proposals',0)+printer.get('complex_proposals',0)==1
        and current.get('enabled')is False and current.get('owned')is False and current.get('waiting_for_server')is False
        and type(current.get('travel_pending',0))is int and current.get('travel_pending',0)in(0,1)
        and(current.get('travel_pending',0)==0 or current.get('failure')==reply['detail'])
        and mask.get('active')is True and mask.get('count')==1 and mask.get('placement_key')==key
        and prior_intent.get('action')=='native'and prior_intent.get('op')=='projection_batch_set'
        and prior_intent.get('params',{}).get('positions')==targets and prior_intent['params'].get('placement_key')==key
        and prior.get('phase')=='done'and prior.get('world_session')==world
        and inventory_counts(prior)==inventory_counts(reply)==inventory_counts(state)
        and bool(event)and event.get('request_id')==reply.get('id')and event.get('op')=='professional_print'
        and event.get('phase')=='error'and event.get('detail')==reply['detail']and event.get('world_session')==world
        and event.get('inventory_delta')=={}and event.get('health_before')==event.get('health_after')==state.get('health')==20
        and event.get('revision_before')==prior.get('control_revision')
        and event.get('revision_after')==reply.get('control_revision')==state.get('control_revision')
        and event.get('params',{}).get('task_session')==task
        and state.get('screen')==''and not state.get('navigating')and not state.get('native_material_busy')and not state.get('pending_scan')
        and isinstance(state.get('movement_keys'),dict)and not any(state['movement_keys'].values()))
