"""Fetch one exact material target across several approved live depots."""


def inventory_count(state, item):
    return sum(row.get('count', 0) for row in state.get('inventory', [])
               if row.get('slot', 100) < 36 and row.get('item') == item)


def snapshot_sources(config, item, server, dimension, region):
    approved = {(row['x'], row['y'], row['z'])
                for row in config.get('projectionSupplySources', [])
                if row.get('server') == server and row.get('dimension') == dimension}
    found = {}
    for snapshot in config.get('storageSnapshots', []):
        pos = (snapshot['x'], snapshot['y'], snapshot['z'])
        if pos not in approved or not region(pos):
            continue
        count = sum(row.get('count', 0) for row in snapshot.get('items', [])
                    if row.get('id') == item)
        if count > 0:
            candidate = (snapshot.get('lastSeenEpochMillis', 0), count, pos)
            if pos not in found or candidate[:2] > found[pos][:2]:
                found[pos] = candidate
    ordered = sorted(found.values(), key=lambda row: (-row[0], -row[1]))
    return [list(row[2]) for row in ordered]


def fetch_exact(client, item, target, sources):
    if not item.startswith('minecraft:') or target < 1:
        raise ValueError('An exact positive Minecraft material target is required')
    receipts = []
    for pos in sources:
        before = inventory_count(client.status(), item)
        if before >= target:
            return receipts
        reply = client.fetch(pos, {item.removeprefix('minecraft:'): target})
        after = inventory_count(client.status(), item)
        receipts.append({'pos': list(pos), 'before': before, 'after': after,
                         'phase': reply.get('phase'),
                         'shortfall': reply.get('shortfall')})
        if after < before:
            raise RuntimeError('Depot transfer reduced carried material')
        if after >= target:
            return receipts
        if reply.get('phase') != 'waiting' or not reply.get('shortfall'):
            raise RuntimeError('Depot did not confirm a simple material shortfall')
    raise RuntimeError(f'Approved depots hold only {inventory_count(client.status(), item)} of {target} {item}')
