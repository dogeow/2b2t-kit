"""Prove a single rejected plain-cube attempt; never manufacture a positive ACK.

Pinned host packet observation plus two later complete scene/inventory frames
can settle a negative result. Missing packet evidence remains unresolved.
"""
from copy import deepcopy
from material_plan import inventory_counts
from printer_partial_interval import HOST_HASHES, REASON, AIR_STATES


def prove(pending, reply, frames, hashes):
    p = reply.get('professional_printer') or {}
    proposal = p.get('last_proposal') or {}
    owner = reply.get('supervision_lease') or {}
    positions = pending.get('positions') or []
    item = pending.get('item')
    target_text = proposal.get('target')
    try:
        target = [int(v.strip()) for v in target_text.split(',')]
    except (AttributeError, ValueError):
        raise RuntimeError('Rejected printer target is absent')
    sent, update = proposal.get('sent_tick'), proposal.get('server_update_tick')
    if (hashes != HOST_HASHES or reply.get('phase') != 'waiting'
            or reply.get('detail') != REASON or reply.get('outcome_pending') is not True
            or reply.get('server_confirmed') is not False
            or not positions or len({tuple(v) for v in positions}) != len(positions)
            or any(not isinstance(v, list) or len(v) != 3 or any(type(n) is not int for n in v) for v in positions)
            or target not in positions or item != 'minecraft:dark_oak_planks'
            or {tuple(v) for v in reply.get('bounded_targets', [])} != {tuple(v) for v in positions}
            or reply.get('bounded_target_count') != len(positions)
            or p.get('fast_proposals') != 1 or p.get('complex_proposals') != 0
            or p.get('server_confirmed') != 0 or p.get('travel_pending') != 1
            or any(p.get(k) is not False for k in ('enabled', 'owned', 'waiting_for_server'))
            or p.get('failure') != '' or proposal.get('interaction_seen') is not True
            or proposal.get('interaction_matches_proposal') is not True
            or proposal.get('server_update_seen') is not True
            or proposal.get('server_update_before_tracked_send') is True
            or type(sent) is not int or type(update) is not int or not 0 <= sent < update
            or proposal.get('server_update_state') not in AIR_STATES
            or proposal.get('expected') != 'Block{'+item+'}'
            or proposal.get('final_target') != 'Block{'+item+'}'
            or proposal.get('hand') != item or proposal.get('ack_final') is True
            or not owner.get('id') or owner.get('kind') != 'materials'
            or not reply.get('world_session') or not reply.get('placement_key') or len(frames) != 2):
        raise RuntimeError('Exact single server-rejected plain-cube attempt is unproved')
    low = [min(v[i] for v in positions) for i in range(3)]
    high = [max(v[i] for v in positions) for i in range(3)]
    previous = reply['time']
    times = []
    for observation in frames:
        command = observation.get('command') or {}
        f = observation.get('result') or {}
        bounds = command.get('params') or {}
        lo, hi = bounds.get('min'), bounds.get('max')
        if (command.get('action') != 'native' or command.get('op') != 'scan'
                or bounds.get('details') is not True or not isinstance(lo, list) or not isinstance(hi, list)
                or len(lo) != 3 or len(hi) != 3 or any(type(v) is not int for v in lo + hi)
                or not all(lo[i] <= low[i] <= high[i] <= hi[i] for i in range(3))):
            raise RuntimeError('Original scan intent does not cover every pending target')
        volume = 1
        for i in range(3): volume *= hi[i] - lo[i] + 1
        rows = {tuple(v['pos']): v for v in f.get('blocks', [])}
        if (f.get('phase') != 'done' or f.get('world_session') != reply['world_session']
                or f.get('connected') is not True or f.get('health') != 20
                or f.get('manual_movement') is not False or f.get('screen') != ''
                or any(f.get(k) != reply.get('control_revision') for k in ('control_revision', 'scan_start_revision', 'scan_end_revision'))
                or f.get('professional_printer') != p
                or any((f.get('supervision_lease') or {}).get(k) != owner.get(k)
                       for k in ('id', 'kind', 'job_session', 'world_session'))
                or (f.get('projection_selection') or {}).get('key') != reply['placement_key']
                or (f.get('menu') or {}).get('cursor', {}).get('count') != 0
                or f.get('scan_cells_read') != volume or f.get('scan_total_cells') != volume
                or f.get('unloaded_chunks', 0) or f.get('time', 0) <= previous
                or dict(inventory_counts(f)) != pending['before']
                or any(rows.get(tuple(v), {}).get('state', 'Block{minecraft:air}') not in AIR_STATES for v in positions)):
            raise RuntimeError('Stopped rejected proposal scene/inventory is unproved')
        previous = f['time']; times.append(previous)
    return {'classification': 'single_plain_cube_server_rejection',
            'source_request': reply['id'], 'world_session': reply['world_session'],
            'placement_key': reply['placement_key'], 'target': target,
            'material_debit': 0, 'placement_credit': 0, 'original_mask_complete': False,
            'positive_ack_created': False, 'original_request_replayed': False,
            'observed_times': times, 'host_hashes': deepcopy(hashes)}
