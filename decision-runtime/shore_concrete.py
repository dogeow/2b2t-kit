"""Harden carried concrete powder at a verified, sheltered shoreline cell.

The native maker performs real place/break/pickup interactions. This wrapper
keeps batches small, returns to the same support after each pickup, and stops
on any ambiguous result instead of replaying a possibly completed batch.
"""

import argparse
import json
from pathlib import Path

from material_client import MaterialClient


def item_count(state, item):
    return sum(slot['count'] for slot in state['inventory'] if slot['item'] == item)


def block_state(rows, pos):
    return next((row['state'] for row in rows if row['pos'] == list(pos)), 'Block{minecraft:air}')


def shoreline_water_sides(rows, support, expected_state, residual_solid=None):
    x, y, z = support
    if block_state(rows, support) != expected_state:
        raise RuntimeError('Concrete support changed')
    cell = [x, y + 1, z]
    observed_cell = block_state(rows, cell)
    if not observed_cell.startswith('Block{minecraft:water}') and observed_cell != f'Block{{{residual_solid}}}':
        raise RuntimeError('Concrete cell is not water: ' + observed_cell)
    sides = sum(block_state(rows, [x + dx, y + 1, z + dz]).startswith('Block{minecraft:water}')
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    if sides not in (1, 2):
        raise RuntimeError('Concrete cell must touch water on only one or two sides')
    return sides


def reconcile_batch(before, after, powder, solid, count):
    used = item_count(before, powder) - item_count(after, powder)
    recovered = item_count(after, solid) - item_count(before, solid)
    if used != count or recovered != count:
        raise RuntimeError(f'Concrete batch is incomplete: powder used={used}, solid recovered={recovered}, expected={count}')
    return {'powder_used': used, 'solid_recovered': recovered}


def convert(client, support, expected_state, powder, solid, count, batch_size=8, out=None,
            waypoint=None, staging=None, stand_block=None):
    if not 1 <= count <= 64 or not 1 <= batch_size <= 16:
        raise ValueError('Count must be 1..64 and batch size 1..16')
    start = client.status()
    if item_count(start, powder) < count:
        raise RuntimeError('Carried powder is insufficient')
    x, y, z = support
    # Flight over long distances is only used to reach a known vicinity. Near
    # the worksite, use the verified block-route navigator via a staging block.
    if max(abs(start['pos'][0]-x), abs(start['pos'][2]-z)) > 96:
        if waypoint is None:
            raise RuntimeError('Work cell is unloaded; provide a safe nearby waypoint')
        arrived = client.request('navigate', target=list(waypoint), arrival=2, seconds=150)
        if arrived.get('phase') != 'done':
            raise RuntimeError('Safe worksite waypoint was not reached')
    near = client.status()
    if max(abs(near['pos'][0]-x), abs(near['pos'][2]-z)) > 8:
        if staging is None:
            raise RuntimeError('Work cell is unloaded; provide a visible staging block')
        observed = client.request('scan', min=list(staging), max=list(staging))['blocks']
        state = block_state(observed, staging)
        if state == 'Block{minecraft:air}' or 'minecraft:water' in state:
            raise RuntimeError('Staging block is not loaded or has changed')
        client.checked('approach_block', pos=list(staging), face='up', expected_state=state, seconds=120)
    scan = client.request('scan', min=[x-1, y, z-1], max=[x+1, y+2, z+1], details=True)
    sides = shoreline_water_sides(scan['blocks'], support, expected_state, solid)
    result = {'support': list(support), 'water_sides': sides, 'requested': count, 'batches': []}
    cell = [x, y+1, z]
    if block_state(scan['blocks'], cell) == f'Block{{{solid}}}':
        client.checked('approach_block', pos=cell, face='up', expected_state=f'Block{{{solid}}}', seconds=120)
        client.checked('select_item', item=powder)
        before = client.status()
        recovered = client.request('concrete_batch', support=list(support), expected_state=expected_state,
                                   powder=powder, target_count=1, seconds=120)
        after = client.status()
        reopened = client.request('scan', min=list(support), max=[x, y+2, z])['blocks']
        if (recovered.get('phase') != 'done' or
                item_count(after, powder) != item_count(before, powder) or
                item_count(after, solid) != item_count(before, solid)+1 or
                not block_state(reopened, cell).startswith('Block{minecraft:water}')):
            raise RuntimeError('Residual concrete recovery was not confirmed; do not place more powder')
        result['residual_recovered'] = 1
    done = 0
    while done < count:
        n = min(batch_size, count-done)
        if stand_block is not None:
            marker = block_state(client.request('scan', min=list(stand_block), max=list(stand_block))['blocks'], stand_block)
            if marker == 'Block{minecraft:air}' or 'minecraft:water' in marker:
                raise RuntimeError('Dry standing marker changed')
            client.checked('approach_block', pos=list(stand_block), face='up', expected_state=marker,
                           stand_distance=.75, seconds=120)
            feet = client.status()['pos']
            if abs(feet[0]-(x+.5))<.9 and abs(feet[2]-(z+.5))<.9:
                raise RuntimeError('Standing position overlaps the powder cell')
        else:
            client.checked('approach_block', pos=list(support), face='up', expected_state=expected_state, seconds=120)
        client.checked('select_item', item=powder)
        before = client.status()
        batch = client.request('concrete_batch', support=list(support), expected_state=expected_state,
                               powder=powder, target_count=n, seconds=120)
        after = client.status()
        entry = {'count': n, 'phase': batch.get('phase'), 'detail': batch.get('detail'),
                 'powder_before': item_count(before, powder), 'powder_after': item_count(after, powder),
                 'solid_before': item_count(before, solid), 'solid_after': item_count(after, solid)}
        result['batches'].append(entry)
        if out is not None:
            Path(out).mkdir(parents=True, exist_ok=True)
            (Path(out)/'progress.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        if batch.get('phase') != 'done':
            raise RuntimeError('Native concrete batch stopped: ' + str(batch.get('detail')))
        entry.update(reconcile_batch(before, after, powder, solid, n))
        done += n
    result['completed'] = done
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--support', type=int, nargs=3, required=True)
    parser.add_argument('--expected-state', required=True)
    parser.add_argument('--powder', required=True)
    parser.add_argument('--solid', required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--waypoint', type=float, nargs=3)
    parser.add_argument('--staging', type=int, nargs=3)
    parser.add_argument('--park-high', type=float, nargs=3,
                        help='Stay online with PvE guard only after a verified high hover')
    parser.add_argument('--stand-block', type=int, nargs=3,
                        help='Verified dry marker near the water cell; prevents standing over fresh powder')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    root = '/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation'
    client = MaterialClient(root, args.out,
                            remote_finish='guard' if args.park_high else 'disconnect',
                            park_target=args.park_high)
    try:
        result = convert(client, args.support, args.expected_state, args.powder, args.solid,
                         args.count, args.batch_size, args.out, args.waypoint, args.staging, args.stand_block)
        (args.out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)
    finally:
        client.finish()


if __name__ == '__main__':
    main()
