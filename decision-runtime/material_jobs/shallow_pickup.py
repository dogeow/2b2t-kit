"""A bounded wet-foot pickup with a mandatory return to witnessed dry air."""
from pathlib import Path
import math
import time

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .protocol import JobBlocked, JobPaused


AIR = 'Block{minecraft:air}'
SUPPORTS = {'Block{minecraft:dirt}', 'Block{minecraft:stone}', 'Block{minecraft:cobblestone}'}
WATER = {'Block{minecraft:water}[level='+str(n)+']' for n in range(16)}


def current_owner(client, state):
    lease = state.get('supervision_lease') or {}
    return (state.get('connected') is True and state.get('world_session') == client.world
            and lease.get('kind') == 'materials' and lease.get('job_session') == client.task
            and lease.get('world_session') == client.world
            and lease.get('revision') == state.get('control_revision') == client.rev
            and not state.get('manual_movement') and not state.get('screen'))


def plan(frame, state, support, return_y, low, high):
    """Sparse air is usable only inside this complete, coherent scan."""
    volume = math.prod(b-a+1 for a, b in zip(low, high))
    predictions = frame.get('scan_predictions') or {}
    if (frame.get('world_session') != state.get('world_session')
            or frame.get('scan_start_revision') != frame.get('scan_end_revision')
            or frame.get('scan_end_revision') != state.get('control_revision')
            or frame.get('scan_coherent') is not True
            or frame.get('scan_cells_read') != volume or frame.get('scan_total_cells') != volume
            or predictions.get('complete') is not True or predictions.get('pending_count') != 0):
        raise JobBlocked('Shallow pickup needs a complete current unpredicted column scan')
    x, y, z = support
    rows = {tuple(v['pos']): v for v in frame['blocks']}
    if rows.get(tuple(support), {}).get('state') not in SUPPORTS:
        raise JobBlocked('Observed dry solid landing support is required')
    top = y+1
    for level in range(top, high[1]+1):
        if rows.get((x, level, z), {}).get('state', AIR) not in WATER | {AIR}:
            raise JobBlocked('Pickup and return column contains an obstruction or non-water hazard')
    water = [level for level in range(top, high[1]+1)
             if rows.get((x, level, z), {}).get('state') in WATER]
    if not water:
        raise JobBlocked('Use ordinary dry pickup for a dry column')
    pos = state['pos']
    if (not all(.32 <= pos[i]-math.floor(pos[i]) <= .68 for i in (0, 2))
            or math.floor(pos[0]) != x or math.floor(pos[2]) != z
            or not 0 <= pos[1]-(top-.1) <= 3):
        raise JobBlocked('Recenter in the observed aperture before shallow pickup')
    dry_min = max(water)+1.5
    if return_y-.7 < dry_min:
        raise JobBlocked('Return must clear water despite normal navigation altitude tolerance')
    return {'target': [x+.5, top-.1, z+.35], 'return_target': [x+.5, return_y, z+.35],
            'landing_min': top, 'landing_max': top+.75, 'dry_min': dry_min}


def collect(client, support, expected_item, target_total, out, *, return_y=64.3, wait_seconds=4):
    """No mining or placement; callers must first clear the witnessed pickup column."""
    if (not isinstance(support, (list, tuple)) or len(support) != 3
            or any(type(n) is not int for n in support) or type(target_total) is not int
            or target_total < 1 or not .1 <= wait_seconds <= 4 or not math.isfinite(return_y)):
        raise ValueError('Bounded pickup parameters required')
    out = Path(out); out.mkdir(exist_ok=False)
    state = client.status()
    if (not current_owner(client, state) or state.get('health', 0) < 19
            or state.get('air_supply', 0) < 285 or state.get('oxygen_bonus', 0) < 3
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or not state.get('auto_log') or not state.get('flight')):
        raise JobBlocked('Healthy guarded owner, respiration III, flight and full air reserve required')
    x, y, z = support
    low = [x-1, y, z-1]; high = [x+1, math.ceil(return_y+1.8), z+1]
    if high[1]-y > 12 or high[1] <= y:
        raise JobBlocked('Pickup return column is outside the finite local scope')
    frame = client.request('scan', min=low, max=high, details=True, include_predictions=True)
    write_json(out/'column.json', frame)
    route = plan(frame, client.status(), support, return_y, low, high)
    write_json(out/'route.json', route)
    if inventory_counts(state)[expected_item] >= target_total and state['pos'][1] >= route['dry_min'] and not state.get('under_water'):
        return {'complete': True, 'already_collected': True, 'movement_sent': False, 'returned_to_dry_air': True}
    try:
        if inventory_counts(client.status())[expected_item] < target_total:
            reply = client.request('navigate', target=route['target'], arrival=.1, air_only=False, seconds=12)
            write_json(out/'landing.json', reply); state = client.status()
            if (reply.get('phase') != 'done' or not current_owner(client, state)
                    or state.get('health', 0) < 19 or state.get('air_supply', 0) < 280
                    or not route['landing_min'] <= state['pos'][1] <= route['landing_max']):
                raise JobBlocked('Actual supported shallow position was not verified')
            if state.get('under_water'):
                client.checked('air_return_set', target=[x+.5, state.get('air_return_y', 65), z+.35])
        deadline = time.monotonic()+wait_seconds
        while inventory_counts(client.status())[expected_item] < target_total:
            if time.monotonic() >= deadline:
                raise JobBlocked('Original drops not recovered; return to dry air without replay')
            time.sleep(.1)
        write_json(out/'collected.json', {'item': expected_item, 'inventory_total': inventory_counts(client.status())[expected_item]})
    finally:
        # A user takeover ends this owner; never reclaim control in cleanup.
        state = client.status()
        if not current_owner(client, state):
            raise JobPaused('Control was handed over; pickup cleanup sent no movement')
        if current_owner(client, state):
            reply = client.request('navigate', target=route['return_target'], arrival=.1, air_only=False, seconds=15)
            write_json(out/'return.json', reply); state = client.status()
            if (reply.get('phase') != 'done' or state['pos'][1] < route['dry_min']
                    or state.get('under_water') or state.get('air_supply', 0) < 260):
                raise JobBlocked('Dry-air return is unproved; retain the observed route and receipts')
    result = {'complete': True, 'item': expected_item, 'target_total': target_total,
              'health': state['health'], 'air_supply': state['air_supply'], 'returned_to_dry_air': True}
    write_json(out/'result.json', result)
    return result
