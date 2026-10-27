"""Reuse an owned server quote when there is no wanted offer; never select payment."""
from copy import deepcopy
from villager_trading import book_matches


def unwanted_quote_observation(merchant,targets,state,*,expected_uuid,expected_world):
    try:
        menu=state['menu'];lease=state['supervision_lease']
        if(not isinstance(targets,dict)or not targets
           or any(not isinstance(k,str)or type(v)is not int or v<1 for k,v in targets.items())
           or state['connected']is not True or state['health']!=20 or state['manual_movement']is not False
           or state['world_session']!=expected_world or lease['world_session']!=expected_world
           or menu['type']!='MerchantMenu'or menu['material_owned']is not True
           or menu['merchant']!=merchant or menu['cursor']['count']!=0 or any(v['count']for v in menu['slots'][:3])
           or merchant['protocol']!=1 or merchant['owned']is not True or merchant['owner_task']!=lease['job_session']
           or merchant['villager_uuid']!=expected_uuid or merchant['level']!=1 or merchant['trader_xp']!=0
           or merchant['observation_scope']!='current_server_received_merchant_menu_not_trade_completion'
           or not merchant['opening_request_id']or not merchant['offers']or any(o['uses']!=0 for o in merchant['offers'])
           or any(book_matches(o['result'],name,level)for o in merchant['offers']for name,level in targets.items())):
            return None
        return {'complete':True,'pending':None,'world_session':expected_world,'uuid':expected_uuid,
                'quote':deepcopy(merchant),'locked':False,'book_purchased':False,'goal_complete':False,
                'no_wanted_offer':True,'no_native_trade_action_sent':True,
                'scope':'planner_observation_of_existing_owned_server_quote_not_a_transaction_or_new_attestation'}
    except(KeyError,TypeError,ValueError):return None
