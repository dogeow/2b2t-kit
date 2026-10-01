"""Reject a successful phase that lacks the corresponding native terminal proof."""
def verified(op,reply,world,request_id,params):
    if op not in ('mine_block','recover_shulker','professional_print'):
        return True
    if op!='professional_print' and (params.get('dry_paving_guard') is True or params.get('terrain_replace_guard') is True):
        return True  # These existing guarded operations have their own stricter proof paths.
    if (not isinstance(request_id,str) or not request_id or reply.get('id')!=request_id
            or reply.get('world_session')!=world or reply.get('server_confirmed') is not True
            or reply.get('outcome_pending') is not False):return False
    if op=='professional_print':
        cells=reply.get('bounded_targets');n=reply.get('bounded_target_count')
        if (reply.get('confirmation_scope')!='current_bounded_mask_distinct_exact_final_server_updates'
                or reply.get('full_projection_confirmed') is not False or type(n)is not int or n<1
                or not isinstance(cells,list) or len(cells)!=n
                or any(not isinstance(p,list) or len(p)!=3 or any(type(v)is not int for v in p) for p in cells)
                or len({tuple(p) for p in cells})!=n or not isinstance(reply.get('placement_key'),str)
                or not reply['placement_key']):return False
        return True
    sequence=reply.get('native_sequence');ack=reply.get('server_ack_sequence');state=reply.get('server_observed_state')
    allowed=('Block{minecraft:air}','Block{minecraft:cave_air}','Block{minecraft:void_air}')
    removed=state in allowed or params.get('underwater_gravel') is True and isinstance(state,str) and state.startswith('Block{minecraft:water}')
    return (reply.get('confirmation_scope')=='single_target_server_block_update_and_native_sequence_ack'
            and reply.get('server_update_seen') is True and type(sequence)is int and sequence>=0
            and type(ack)is int and ack>=sequence and reply.get('mining_target')==params.get('pos') and removed)
