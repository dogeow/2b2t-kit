"""Resume a guarded sand trip across surveyed dry patches without rescanning exhausted ones.

The patch manifest is only a route hint. The imported quarry worker performs a
fresh loaded-world scan before every break and confirms each inventory gain.
This driver retains one material safety lease across patches and finishes only
when the backpack cannot accept another sand block, the carried goal is met,
or every supplied patch has no safe sand left.
"""

import argparse
import json
import math
import re
import time
from pathlib import Path

from material_client import MaterialClient
from material_stage_gate import require_gravel_complete
from material_trip_policy import carried, room_for_item, trip_complete
from surface_sand_harvest import (APPROVED_CHESTS, SAND, harvest, safe_state,
                                  validate_region)

ROOT = Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation')
PROJECTION = 'SpaceX 星舰 · 白色生存版 123格'
LEDGER_VERSION = 1
SKIPPABLE = {'exhausted'}


def minimum_partial_slack(amount):
    if not isinstance(amount, int) or amount < 0:
        raise ValueError('A nonnegative counted item amount is required')
    return (-amount) % 64 if amount else 0


def conservative_storage_after_gravel(audit, incoming_gravel=250, incoming_sand=722):
    """Lower bound on sand room using only aggregate counts and empty slots.

    Simulate chest order and guaranteed gravel partial-stack merges. Real slot
    layouts may provide *more* capacity, never less, if this old audit still
    represents the same containers and no other transfers intervene.
    """
    if incoming_gravel < 0 or incoming_sand < 0:
        raise ValueError('Incoming material amounts cannot be negative')
    chests = audit.get('chests', [])
    if not chests:
        raise ValueError('A counted chest audit is required')
    remaining = incoming_gravel
    after = []
    sand_partial = 0
    for chest in chests:
        free = chest.get('free_slots')
        items = chest.get('items')
        if not isinstance(free, int) or free < 0 or not isinstance(items, dict):
            raise ValueError('Chest free slots and item totals must be counted')
        gravel = items.get('minecraft:gravel', 0)
        sand = items.get(SAND, 0)
        sand_partial += minimum_partial_slack(sand)
        merged = min(remaining, minimum_partial_slack(gravel))
        remaining -= merged
        new_slots = min(free, (remaining + 63) // 64)
        placed_in_new = min(remaining, new_slots * 64)
        remaining -= placed_in_new
        after.append({'pos': chest.get('pos'), 'free_slots_before': free,
                      'free_slots_after_gravel': free - new_slots,
                      'guaranteed_gravel_merge': merged,
                      'gravel_in_new_slots': placed_in_new})
    if remaining:
        raise RuntimeError(f'Counted chests cannot guarantee room for {remaining} incoming gravel')
    free_sand_room = sum(row['free_slots_after_gravel'] * 64 for row in after)
    guaranteed_sand_room = free_sand_room + sand_partial
    return {'gravel_to_store': incoming_gravel, 'new_sand_to_store': incoming_sand,
            'free_slots_after_gravel': sum(row['free_slots_after_gravel'] for row in after),
            'empty_slot_sand_capacity': free_sand_room,
            'existing_sand_partial_capacity': sand_partial,
            'guaranteed_new_sand_capacity': guaranteed_sand_room,
            'sand_capacity_margin': guaranteed_sand_room - incoming_sand,
            'early_crafting_needed_for_space': guaranteed_sand_room < incoming_sand,
            'per_chest': after,
            'evidence_scope': 'old aggregate audit only; refresh live chest menus before depositing'}


def patch_key(patch, state):
    return (state['server'], state['dimension'], state['world_session'],
            patch['id'], tuple(patch['region']))


def validate_plan(plan, state, initial_pos):
    if plan.get('version') != 1 or not isinstance(plan.get('patches'), list) or not plan['patches']:
        raise ValueError('A version-1 nonempty dry sand frontier is required')
    for name in ('server', 'dimension', 'world_session'):
        if plan.get(name) != state.get(name):
            raise RuntimeError('Sand frontier belongs to another world/session')
    center = plan.get('site_center')
    if not isinstance(center, list) or len(center) != 2 or not all(isinstance(v, int) for v in center):
        raise ValueError('Starship X/Z center is required')
    seen_ids = set()
    regions = []
    for patch in plan['patches']:
        name = patch.get('id')
        region = patch.get('region')
        park = patch.get('park_high')
        evidence = patch.get('verification')
        if not isinstance(name, str) or re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', name) is None or name in seen_ids:
            raise ValueError('Every sand patch needs a unique safe id')
        seen_ids.add(name)
        if not isinstance(region, list) or len(region) != 6 or not all(isinstance(v, int) for v in region):
            raise ValueError('Every sand patch needs six integer bounds')
        low, high = region[:3], region[3:]
        validate_region(low, high)
        if not isinstance(park, list) or len(park) != 3 or not all(isinstance(v, (int, float)) for v in park):
            raise ValueError('Every patch needs a known high safety park')
        if not high[1] + 25 <= park[1] <= 320:
            raise ValueError('Sand patch high park lacks vertical clearance')
        midpoint = [(low[0] + high[0] + 1) / 2, park[1], (low[2] + high[2] + 1) / 2]
        if math.hypot(midpoint[0] - park[0], midpoint[2] - park[2]) > 16:
            raise ValueError('Patch park is not over its quarry')
        near_x = min(max(center[0], low[0]), high[0])
        near_z = min(max(center[1], low[2]), high[2])
        if math.hypot(near_x - center[0], near_z - center[1]) < 96:
            raise ValueError('Sand quarry enters the protected Starship radius')
        if math.hypot(midpoint[0] - initial_pos[0], midpoint[2] - initial_pos[2]) > 480:
            raise ValueError('Patch exceeds the single-session 480-block worksite reach')
        if not isinstance(evidence, dict) or evidence.get('source') != 'automation_scan' \
                or evidence.get('server') != state['server'] \
                or evidence.get('dimension') != state['dimension'] \
                or evidence.get('world_session') != state['world_session'] \
                or not isinstance(evidence.get('dry_sand_count'), int) \
                or evidence['dry_sand_count'] < 1 \
                or not isinstance(evidence.get('at_ms'), int) \
                or evidence['at_ms'] > state.get('time', 0):
            raise ValueError('Patch needs a same-world recorded dry-sand scan hint')
        for previous in regions:
            if all(region[i] <= previous[i + 3] and previous[i] <= region[i + 3]
                   for i in range(3)):
                raise ValueError('Overlapping sand patches would rescan the same blocks')
        regions.append(region)
    return plan


class SandFrontierLedger:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if self.data.get('version') != LEDGER_VERSION or not isinstance(self.data.get('entries'), list):
                raise ValueError('Unknown sand frontier ledger; refusing to overwrite it')
        else:
            self.data = {'version': LEDGER_VERSION, 'entries': []}

    def get(self, patch, state):
        key = patch_key(patch, state)
        return next((entry for entry in self.data['entries']
                     if (entry.get('server'), entry.get('dimension'), entry.get('world_session'),
                         entry.get('patch_id'), tuple(entry.get('region', []))) == key), None)

    def record(self, patch, state, status, **facts):
        if status not in {'exhausted', 'partial', 'interrupted'}:
            raise ValueError('Unsupported patch status')
        entry = self.get(patch, state)
        if entry is None:
            entry = {'server': state['server'], 'dimension': state['dimension'],
                     'world_session': state['world_session'], 'patch_id': patch['id'],
                     'region': patch['region']}
            self.data['entries'].append(entry)
        entry.update(status=status, at_ms=int(time.time() * 1000), **facts)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + '.tmp')
        temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2))
        temporary.replace(self.path)
        return entry


def drive(client, plan, ledger, out, target_carried=722, harvest_fn=harvest):
    if not 1 <= target_carried <= 2304:
        raise ValueError('Sand carried target must be 1..2304')
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    initial = client.status()
    safe_state(initial)
    validate_plan(plan, initial, getattr(client, 'anchor', initial['pos']))
    result = {'world_session': initial['world_session'], 'before': carried(initial, SAND),
              'target_carried': target_carried, 'patches': [], 'skipped_exhausted': []}
    for patch in plan['patches']:
        state = client.status()
        safe_state(state)
        if trip_complete(state, SAND, target_carried):
            break
        previous = ledger.get(patch, state)
        if previous is not None and previous.get('status') in SKIPPABLE:
            result['skipped_exhausted'].append(patch['id'])
            continue
        low, high = patch['region'][:3], patch['region'][3:]
        park = patch['park_high']
        target = [(low[0] + high[0] + 1) / 2, park[1], (low[2] + high[2] + 1) / 2]
        if math.dist(state['pos'], target) > 2:
            reached = client.request('navigate', target=target, arrival=2, seconds=120)
            if reached.get('phase') != 'done':
                raise RuntimeError('High arrival at sand patch failed: ' + str(reached.get('detail')))
        patch_out = out / patch['id']
        before = carried(client.status(), SAND)
        try:
            sample = harvest_fn(client, low, high, target_carried, patch_out)
        except Exception as error:
            ledger.record(patch, state, 'interrupted', error=str(error)[:300])
            raise
        if (sample.get('before') != before or sample.get('after') != carried(client.status(), SAND)
                or sample.get('gained') != sample['after'] - before):
            raise RuntimeError('Patch receipt does not match observed carried sand')
        patch_out.mkdir(parents=True, exist_ok=True)
        temporary = patch_out / 'result.tmp'
        temporary.write_text(json.dumps(sample, ensure_ascii=False, indent=2))
        temporary.replace(patch_out / 'result.json')
        status = 'partial' if sample.get('bag_full') or sample.get('target_reached') else 'exhausted'
        ledger.record(patch, client.status(), status, gained=sample['gained'],
                      carried_after=sample['after'], result_path=str(patch_out / 'result.json'))
        result['patches'].append({'id': patch['id'], 'gained': sample['gained'],
                                  'carried_after': sample['after'], 'status': status})
        temporary = out / 'progress.tmp'
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        temporary.replace(out / 'progress.json')
    end = client.status()
    result.update(after=carried(end, SAND), gained=carried(end, SAND) - result['before'],
                  bag_full=room_for_item(end, SAND) == 0,
                  target_reached=carried(end, SAND) >= target_carried,
                  patches_exhausted=not trip_complete(end, SAND, target_carried),
                  health=end['health'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--gravel-audit', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--target-carried', type=int, default=722)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    audit = json.loads(args.gravel_audit.read_text())
    preflight = json.loads((ROOT / 'status.json').read_text())
    require_gravel_complete(audit, preflight, 836, APPROVED_CHESTS)
    validate_plan(plan, preflight, preflight['pos'])
    ledger = SandFrontierLedger(args.ledger)
    first_park = plan['patches'][0]['park_high']
    client = MaterialClient(ROOT, args.out, remote_finish='guard', park_target=first_park)
    try:
        state = client.status()
        require_gravel_complete(audit, state, 836, APPROVED_CHESTS)
        if state.get('projection_selection', {}).get('name') != PROJECTION:
            raise RuntimeError('Starship projection changed')
        result = drive(client, plan, ledger, args.out, args.target_carried)
        (args.out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        client.finish()


if __name__ == '__main__':
    main()
