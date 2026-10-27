"""Permit only witnessed redundant maxima; never bypass the host's protected book set."""
from villager_trading import TARGETS as HOST_KEEPERS, book_matches

# Keep ten seconds inside the independently enforced native 30-second window.
NATIVE_KEEPER_MAX_AGE_MS = 20_000

# Opportunistic keepers, never required for completion or pursued after required books.
OPTIONAL_MAXIMA = {
    'minecraft:loyalty': 3, 'minecraft:channeling': 1, 'minecraft:riptide': 3,
    'minecraft:blast_protection': 4, 'minecraft:projectile_protection': 4,
    'minecraft:bane_of_arthropods': 5, 'minecraft:quick_charge': 3,
    'minecraft:piercing': 4, 'minecraft:multishot': 1,
    'minecraft:luck_of_the_sea': 3, 'minecraft:lure': 3,
}


def reset_allowed(merchant, targets, locked, proofs, state, *, native_attestations=None, keeper_history_scopes=None):
    """This is an additional planner check; native quote/reset checks still apply."""
    try:
        task = state['supervision_lease']['job_session']
        uid = merchant['villager_uuid']
        if (merchant['protocol'] != 1 or merchant['owned'] is not True
                or merchant['owner_task'] != task or merchant['trader_xp'] != 0
                or merchant['level'] != 1 or any(o['uses'] != 0 for o in merchant['offers'])
                or state['connected'] is not True or state['health'] != 20
                or state['manual_movement'] is not False or not state['world_session']):
            return False
        protected_targets = dict(targets)
        for name, level in OPTIONAL_MAXIMA.items():
            if any(book_matches(o['result'], name, level) for o in merchant['offers']):
                # Keep the first optional maximum. A duplicate needs the same
                # independently witnessed keeper certificate as a required book.
                if name not in locked:
                    return False
                protected_targets[name] = level
        actors = {v['uuid']:v for v in state['loaded_villagers']['villagers']}
        for name, level in protected_targets.items():
            if not any(book_matches(o['result'], name, level) for o in merchant['offers']):
                continue
            # Leave the native seven-book policy untouched; it needs its own fresh certificate.
            if name in HOST_KEEPERS and not native_duplicate_attested(name,level,uid,locked,proofs,state,native_attestations):
                return False
            kept = locked[name]
            proof = proofs[name]
            quote = proof['merchant']
            keeper = actors[kept['villager_uuid']]
            if (kept['villager_uuid'] == uid or kept['level'] != level
                    or kept['server_history_verified'] is not True
                    or proof['complete'] is not True or proof.get('pending')
                    or proof.get('open_roofs') or (proof['world_session'] != state['world_session']
                        and (name in HOST_KEEPERS or not historical_keeper_scope(proof,state,(keeper_history_scopes or{}).get(name))))
                    or proof['keeper_uuid'] != kept['villager_uuid']
                    or quote['villager_uuid'] != kept['villager_uuid'] or quote['trader_xp'] <= 0
                    or not any(book_matches(o['result'], name, level) for o in quote['offers'])
                    or keeper['health'] != 20 or keeper['is_baby'] is not False
                    or keeper['villager']['profession'] != 'minecraft:librarian'):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def native_duplicate_attested(name,level,candidate,locked,proofs,state,attestations):
    """A recent paid other supplier quote permits requesting, never bypassing, the host's own check."""
    try:
        reply=(attestations or{})[name];lease=state['supervision_lease'];old=reply['supervision_lease'];m=reply['menu']['merchant'];kept=locked[name]
        return(reply['connected']is True and reply['health']==20 and reply['manual_movement']is False
            and reply['world_session']==state['world_session'] and type(reply['time'])is int
            and 0<=state['time']-reply['time']<=NATIVE_KEEPER_MAX_AGE_MS
            and old['kind']=='materials'and all(old[k]==lease[k]for k in('id','job_session','world_session'))
            and reply['menu']['material_owned']is True and m['protocol']==1 and m['owned']is True
            and m['owner_task']==lease['job_session']and m['villager_uuid']==kept['villager_uuid']!=candidate
            and m['trader_xp']>0 and m['observation_scope']=='current_server_received_merchant_menu_not_trade_completion'
            and m==proofs[name]['merchant']and any(book_matches(o['result'],name,level)for o in m['offers']))
    except(KeyError,TypeError,ValueError):return False


def historical_keeper_scope(proof,state,certificate):
    from keeper_history_scope import matches
    return matches(certificate,proof,state)
