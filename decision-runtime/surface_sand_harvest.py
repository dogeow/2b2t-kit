"""Mine a bounded dry sand patch for the Starship, keeping one guarded trip open.

This is deliberately a land quarry. It never enters water, opens a cave, or
breaks a block with a nearby block entity. Each server-confirmed block break
must produce a verified sand inventory gain before the next break. Supply is
stored separately after the backpack fills or the requested total is reached.
"""

import argparse
import json
import math
import time
from pathlib import Path

from drop_collection import collect_drop
from material_client import Handoff, MaterialClient
from material_stage_gate import require_gravel_complete
from material_trip_policy import carried, room_for_item, trip_complete
from shore_concrete import block_state

SAND = 'minecraft:sand'
SAND_STATE = 'Block{minecraft:sand}'
BUFFER = 3
APPROVED_CHESTS = ([761019, 64, 797852], [761021, 64, 797852],
                   [761011, 64, 797852], [761015, 64, 797852])


def validate_region(low, high):
    if any(a > b for a, b in zip(low, high)):
        raise ValueError('Region bounds are reversed')
    if high[0] - low[0] > 31 or high[2] - low[2] > 31 or high[1] - low[1] > 15:
        raise ValueError('One dry sand patch is limited to 32×16×32 blocks')


def scan_bounds(low, high):
    return ([low[0] - BUFFER, low[1] - 2, low[2] - BUFFER],
            [high[0] + BUFFER, high[1] + 2, high[2] + BUFFER])


def sand_candidate(rows, pos, index=None):
    x, y, z = pos
    if index is None:
        index = {tuple(row['pos']): row for row in rows}
    sand = index.get((x, y, z))
    if sand is None or sand['state'] != SAND_STATE or (x, y + 1, z) in index:
        return False
    support = index.get((x, y - 1, z))
    if support is None or not support.get('solid', False) or support.get('fluid', False):
        return False
    for dx in range(-BUFFER, BUFFER + 1):
        for dz in range(-BUFFER, BUFFER + 1):
            for dy in range(-3, 4):
                row = index.get((x + dx, y + dy, z + dz))
                if row is None:
                    continue
                if row.get('block_entity', False):
                    return False
                if abs(dy) <= 2 and (row.get('fluid', False)
                                    or row['state'].startswith('Block{minecraft:water}')):
                    return False
    return True


def candidates(rows, low, high, pos):
    rows = list(rows)
    index = {tuple(row['pos']): row for row in rows}
    selected = [tuple(row['pos']) for row in rows
                if row['state'] == SAND_STATE
                and all(low[i] <= row['pos'][i] <= high[i] for i in range(3))
                and sand_candidate(rows, row['pos'], index)]
    selected.sort(key=lambda p: (sum((p[i] + .5 - pos[i]) ** 2 for i in (0, 2)),
                                 abs(p[1] + .5 - pos[1]), -p[1]))
    return [list(p) for p in selected]


def merge_local(rows_by_pos, local, pos):
    """Replace one freshly observed 7×6×7 area without rescanning the quarry."""
    x, y, z = pos
    old_keys = [key for key in rows_by_pos
                if abs(key[0] - x) <= BUFFER and y - 2 <= key[1] <= y + 3
                and abs(key[2] - z) <= BUFFER]
    for key in old_keys:
        del rows_by_pos[key]
    rows_by_pos.update({tuple(row['pos']): row for row in local})


def fresh_sand_drops(before, after, pos):
    previous = {row['uuid'] for row in before.get('entities', [])
                if row.get('type') == 'minecraft:item'}
    return [row for row in after.get('entities', [])
            if row.get('type') == 'minecraft:item' and row['uuid'] not in previous
            and row.get('stack', {}).get('item') == SAND
            and len(row.get('pos', [])) == 3
            and sum((a - (b + .5)) ** 2 for a, b in zip(row['pos'], pos)) <= 36]


def local_scan(client, pos):
    x, y, z = pos
    return client.request('scan', min=[x - BUFFER, y - 2, z - BUFFER],
                          max=[x + BUFFER, y + 3, z + BUFFER], details=True)['blocks']


def safe_state(state):
    if (state.get('health', 0) < 19 or not state.get('guard_armed')
            or state.get('under_water') or state.get('safety_hold', {}).get('active')):
        raise RuntimeError('Guard, dry location, or full-health margin lost')


def under_feet(player_pos, target):
    return (math.floor(player_pos[0]) == target[0]
            and math.floor(player_pos[2]) == target[2]
            and target[1] + 1 <= player_pos[1] < target[1] + 2)


def mine_one(client, pos, expected=SAND_STATE):
    state = client.status()
    safe_state(state)
    if under_feet(state['pos'], pos):
        return {'pos': pos, 'skipped': 'Sand supports the player'}
    if room_for_item(state, SAND) < 1:
        raise RuntimeError('No backpack room for sand')
    fresh = local_scan(client, pos)
    if not sand_candidate(fresh, pos):
        return {'pos': pos, 'skipped': 'Target is no longer a dry exposed sand block'}
    client.checked('select_item', item='minecraft:diamond_shovel')
    before = client.status()
    # Avoid a movement transaction for a block already within reach. The
    # native bridge checks actual reach and returns this exact pre-dispatch
    # error if an approach is needed.
    mined = client.request('mine_block', pos=pos, face='up', expected_state=expected, seconds=20)
    if mined.get('phase') == 'error' and mined.get('detail') == 'Mining target out of reach':
        if not sand_candidate(local_scan(client, pos), pos):
            raise RuntimeError('Sand changed after the out-of-reach rejection')
        approached = client.request('approach_block', pos=pos, face='up',
                                    expected_state=expected, seconds=90)
        if approached.get('phase') == 'waiting':
            raise Handoff('Sand approach yielded control: ' + str(approached.get('detail')))
        if approached.get('phase') != 'done':
            raise RuntimeError('Sand approach failed: ' + str(approached.get('detail')))
        client.checked('select_item', item='minecraft:diamond_shovel')
        if not sand_candidate(local_scan(client, pos), pos):
            raise RuntimeError('Sand changed after approach; no mining replay')
        before = client.status()
        mined = client.request('mine_block', pos=pos, face='up',
                               expected_state=expected, seconds=20)
    if mined.get('phase') != 'done':
        raise RuntimeError('Sand break was not confirmed: ' + str(mined.get('detail')))
    observed_after = local_scan(client, pos)
    if block_state(observed_after, pos) == expected:
        raise RuntimeError('Sand still present after mining reply; stop for server reconciliation')
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        after = client.status()
        safe_state(after)
        if carried(after, SAND) > carried(before, SAND):
            return {'pos': pos, 'sand_gain': carried(after, SAND) - carried(before, SAND),
                    'health': after['health'], 'pickup': 'inventory', '_observed': observed_after}
        drops = fresh_sand_drops(before, after, pos)
        if drops:
            for drop in drops:
                if not collect_drop(client, drop, observation=after):
                    raise RuntimeError('Observed sand drop could not be recovered')
            confirmed = client.status()
            if carried(confirmed, SAND) > carried(before, SAND):
                return {'pos': pos, 'sand_gain': carried(confirmed, SAND) - carried(before, SAND),
                        'health': confirmed['health'], 'pickup': 'drop', '_observed': observed_after}
            raise RuntimeError('Sand pickup reply did not increase inventory')
        time.sleep(.2)
    raise RuntimeError('Sand break produced no verified inventory gain')


def harvest(client, low, high, target_carried, out):
    validate_region(low, high)
    if not 1 <= target_carried <= 2304:
        raise ValueError('Target backpack sand must be 1..2304')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    start = client.status()
    safe_state(start)
    shovel = next((row for row in start.get('inventory', [])
                   if row.get('item') == 'minecraft:diamond_shovel' and row.get('count', 0) == 1), None)
    needed = max(0, target_carried - carried(start, SAND))
    if shovel is None or shovel.get('durability', 0) < min(256, needed) + 32:
        raise RuntimeError('One diamond shovel with a 32-durability reserve is required')
    result = {'bounds': [list(low), list(high)], 'before': carried(start, SAND),
              'target_carried': target_carried, 'blocks': [], 'world_session': start['world_session']}
    blocked = set()
    scan_min, scan_max = scan_bounds(low, high)
    first_scan = client.request('scan', min=scan_min, max=scan_max, details=True)['blocks']
    rows_by_pos = {tuple(row['pos']): row for row in first_scan}
    while not trip_complete(client.status(), SAND, target_carried):
        current = client.status()
        safe_state(current)
        current_shovel = next((row for row in current.get('inventory', [])
                               if row.get('item') == 'minecraft:diamond_shovel' and row.get('count') == 1), None)
        if current_shovel is None or current_shovel.get('durability', 0) < 32:
            raise RuntimeError('Shovel durability reserve reached')
        available = [p for p in candidates(rows_by_pos.values(), low, high, current['pos'])
                     if tuple(p) not in blocked and not under_feet(current['pos'], p)]
        if not available:
            break
        p = available[0]
        record = mine_one(client, p)
        if 'skipped' in record:
            blocked.add(tuple(p))
        merge_local(rows_by_pos, record.pop('_observed', None) or local_scan(client, p), p)
        result['blocks'].append(record)
        result['after'] = carried(client.status(), SAND)
        temporary = out / 'progress.tmp'
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        temporary.replace(out / 'progress.json')
    end = client.status()
    result.update(after=carried(end, SAND), gained=carried(end, SAND) - result['before'],
                  bag_full=room_for_item(end, SAND) == 0,
                  target_reached=carried(end, SAND) >= target_carried,
                  health=end['health'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', nargs=6, type=int, required=True,
                        metavar=('MIN_X', 'MIN_Y', 'MIN_Z', 'MAX_X', 'MAX_Y', 'MAX_Z'))
    parser.add_argument('--target-carried', type=int, required=True)
    parser.add_argument('--gravel-audit', type=Path, required=True)
    parser.add_argument('--site-center', nargs=2, type=int, required=True,
                        metavar=('STARSHIP_X', 'STARSHIP_Z'))
    parser.add_argument('--park-high', nargs=3, type=float, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    low, high = args.region[:3], args.region[3:]
    validate_region(low, high)
    nearest_x = min(max(args.site_center[0], low[0]), high[0])
    nearest_z = min(max(args.site_center[1], low[2]), high[2])
    if math.hypot(nearest_x - args.site_center[0], nearest_z - args.site_center[1]) < 96:
        raise ValueError('Dry sand quarry is too close to the protected Starship site')
    if math.hypot((low[0] + high[0]) / 2 - args.park_high[0],
                  (low[2] + high[2]) / 2 - args.park_high[2]) > 16:
        raise ValueError('High safety park must be above this sand patch')
    if not high[1] + 25 <= args.park_high[1] <= 320:
        raise ValueError('High safety park must clear the whole sand patch by 25 blocks')
    root = '/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation'
    audit = json.loads(args.gravel_audit.read_text())
    preflight = json.loads((Path(root) / 'status.json').read_text())
    require_gravel_complete(audit, preflight, 836, APPROVED_CHESTS)
    if math.hypot(preflight['pos'][0] - args.park_high[0],
                  preflight['pos'][2] - args.park_high[2]) > 480:
        raise ValueError('Stage within 480 blocks of the dry sand patch first')
    client = MaterialClient(root, args.out, remote_finish='guard', park_target=args.park_high)
    try:
        state = client.status()
        require_gravel_complete(audit, state, 836, APPROVED_CHESTS)
        safe_state(state)
        if state.get('projection_selection', {}).get('name') != 'SpaceX 星舰 · 白色生存版 123格':
            raise RuntimeError('Starship projection changed')
        mid = [(low[0] + high[0] + 1) / 2, args.park_high[1],
               (low[2] + high[2] + 1) / 2]
        if math.dist(state['pos'], mid) > 16:
            reached = client.request('navigate', target=mid, arrival=2, seconds=120)
            if reached.get('phase') != 'done':
                raise RuntimeError('High approach to dry sand patch did not finish')
        result = harvest(client, low, high, args.target_carried, args.out)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        client.finish()


if __name__ == '__main__':
    main()
