"""Build or resume a journaled smelting bank on freshly observed dry ground."""
import json
import time
from pathlib import Path

from build_supervisor import stocks
from kit_runtime.journal import write_json
from projection_wood import use_with_margin
from work_access import ApproachUnavailable


FURNACE = 'Block{minecraft:furnace}'
GROUND = ('Block{minecraft:grass_block}', 'Block{minecraft:dirt}')


def _positions(positions):
    result = [list(pos) for pos in positions]
    if (not result or any(len(pos) != 3 or any(type(n) is not int for n in pos) for pos in result)
            or len({tuple(pos) for pos in result}) != len(result)):
        raise ValueError('Furnace positions must be nonempty distinct integer coordinates')
    if any(max(abs(a[0] - b[0]), abs(a[2] - b[2])) < 2
           for i, a in enumerate(result) for b in result[i + 1:]):
        raise ValueError('Keep one clear block between furnace pads')
    return result


def _dry_pad(cells, pos):
    x, level, z = pos
    floor = cells.get((x, level - 1, z), {})
    return (floor.get('solid') and not floor.get('fluid') and not floor.get('block_entity')
            and floor.get('state', '').startswith(GROUND)
            and not any((x, y, z) in cells for y in range(level, level + 3))
            and not any(r.get('fluid') or r.get('block_entity') for p, r in cells.items()
                        if abs(p[0] - x) <= 1 and abs(p[2] - z) <= 1 and level - 1 <= p[1] <= level + 1))


def choose_pads(rows, columns, level, count=6):
    if type(count) is not int or count < 1:
        raise ValueError('A positive furnace count is required')
    cells = {tuple(r['pos']): r for r in rows}
    picked = []
    for x, z in dict.fromkeys(tuple(column) for column in columns):
        pos = [x, level, z]
        if any(max(abs(x - p[0]), abs(z - p[2])) < 2 for p in picked):
            continue
        if not _dry_pad(cells, pos):
            continue
        picked.append(pos)
        if len(picked) == count:
            return picked
    raise RuntimeError('Not enough empty dry pads for the requested furnace bank')


def choose_surface_pads(rows, columns, count=6):
    """Follow observed grass/dirt height; preserve plants and other occupied cells."""
    if type(count) is not int or count < 1:
        raise ValueError('A positive furnace count is required')
    cells = {tuple(r['pos']): r for r in rows}
    picked = []
    for x, z in dict.fromkeys(tuple(column) for column in columns):
        if any(max(abs(x - p[0]), abs(z - p[2])) < 2 for p in picked):
            continue
        levels = sorted((p[1] + 1 for p, row in cells.items()
                         if p[0] == x and p[2] == z and row.get('state', '').startswith(GROUND)), reverse=True)
        for level in levels:
            pos = [x, level, z]
            if _dry_pad(cells, pos):
                picked.append(pos)
                break
        if len(picked) == count:
            return picked
    raise RuntimeError('Not enough observed empty dry surface pads for the furnace bank')


def _scan_pad(client, pos):
    x, y, z = pos
    rows = client.request('scan', min=[x - 1, y - 1, z - 1],
                          max=[x + 1, y + 2, z + 1], details=True)['blocks']
    cells = {tuple(row['pos']): row for row in rows}
    if not _dry_pad(cells, pos):
        raise RuntimeError('Furnace pad is occupied or lost its dry clear surroundings')
    return cells[(x, y - 1, z)]


def inspect_bank(client, positions, journal):
    positions = _positions(positions)
    journal = Path(journal)
    record = json.loads(journal.read_text())
    if record.get('world_session') != client.world:
        raise RuntimeError('Reconfirm furnace ownership after a world transition')
    if record.get('positions') != positions:
        raise RuntimeError('Existing furnace bank plan differs; do not reuse its receipts')
    placed = record.get('placed')
    if not isinstance(placed, list):
        raise RuntimeError('Furnace bank receipts are incomplete')
    expected = {tuple(pos) for pos in positions}
    recorded = [tuple(row.get('pos', [])) for row in placed]
    if len(set(recorded)) != len(recorded) or any(pos not in expected for pos in recorded):
        raise RuntimeError('Furnace bank receipts do not match the plan')
    if record.get('pending'):
        # The previous click may already have reached the server. No replay or
        # automatic adoption based only on a block now occupying the position.
        raise RuntimeError('Unconfirmed furnace placement requires inspection; do not replay')
    if record.get('complete') and len(placed) != len(positions):
        raise RuntimeError('Completed furnace bank is missing placement receipts')
    for row in placed:
        pos = row['pos']
        current = client.request('scan', min=pos, max=pos)['blocks']
        if (len(current) != 1 or current[0].get('pos') != pos
                or not row.get('state', '').startswith(FURNACE)
                or not current[0].get('state', '').startswith(FURNACE)):
            raise RuntimeError('Previously placed furnace changed; preserve the area')
    return record


def build(client, positions, journal, *, resume=False):
    positions = _positions(positions)
    journal = Path(journal)
    if journal.exists():
        if not resume:
            raise RuntimeError('Inspect the existing bank journal rather than re-place furnaces')
        record = inspect_bank(client, positions, journal)
    else:
        if resume:
            raise RuntimeError('No furnace bank journal exists to resume')
        record = {'world_session': client.world, 'positions': positions,
                  'placed': [], 'pending': None, 'complete': False}
    placed = {tuple(row['pos']) for row in record['placed']}
    remaining = [pos for pos in positions if tuple(pos) not in placed]
    if stocks(client.status()).get('minecraft:furnace', 0) < len(remaining):
        raise RuntimeError('Not enough ordinary furnaces for the remaining bank')
    # Validate the complete unbuilt area before consuming the first furnace.
    for pos in remaining:
        _scan_pad(client, pos)
    write_json(journal, record)
    for pos in remaining:
        floor = [pos[0], pos[1] - 1, pos[2]]
        ground = _scan_pad(client, pos)
        client.checked('select_item', item='minecraft:furnace')
        before = stocks(client.status()).get('minecraft:furnace', 0)

        def before_use():
            current = client.status()['pos']
            if (abs(current[0] - pos[0] - .5) < .81 and abs(current[2] - pos[2] - .5) < .81
                    and current[1] < pos[1] + 1 and current[1] + 1.8 > pos[1]):
                raise RuntimeError('Do not place furnace through the player')
            _scan_pad(client, pos)
            record['pending'] = {'pos': pos, 'inventory_before': before}
            write_json(journal, record)

        try:
            use_with_margin(client, floor, ground['state'], 'minecraft:furnace', ('up',), before_use)
        except ApproachUnavailable:
            # This helper raises ApproachUnavailable only when navigation or
            # explicit pre-use rejections prevented every interaction. All
            # uncertain replies still retain the pending receipt.
            record['pending'] = None
            write_json(journal, record)
            raise
        deadline = time.monotonic() + 6
        while True:
            state = client.status()
            actual = client.request('scan', min=pos, max=pos)['blocks']
            if (len(actual) == 1 and actual[0].get('pos') == pos
                    and actual[0]['state'].startswith(FURNACE)
                    and stocks(state).get('minecraft:furnace', 0) == before - 1):
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Furnace placement not confirmed; do not replay')
            time.sleep(.2)
        record['placed'].append({'pos': pos, 'state': actual[0]['state'], 'at_ms': state['time']})
        record['pending'] = None
        write_json(journal, record)
    record['complete'] = True
    write_json(journal, record)
    return record
