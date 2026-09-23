"""Survey a user-chosen Litematica worksite without placing or removing blocks.

The live entrypoint keeps a native materials safety lease for the entire survey
and requests an acknowledged logout when it finishes. Never leave an unattended
player in the world while calculating or editing a large schematic offline.
"""
import argparse
import json
from pathlib import Path

from material_client import MaterialClient


def evaluate(origin, size, support_rows, volume_rows, margin=3):
    """Return observed clearance; reject weak ground and pre-existing work."""
    x0, y0, z0 = origin
    sx, sy, sz = size
    supports = {(row['pos'][0], row['pos'][2]): row for row in support_rows
                if row['pos'][1] == y0 - 1}
    unsupported = []
    for x in range(x0, x0 + sx):
        for z in range(z0, z0 + sz):
            row = supports.get((x, z))
            if not row or not row.get('solid') or row.get('fluid') or row.get('block_entity'):
                unsupported.append([x, y0 - 1, z])
    obstructions = [row for row in volume_rows
                    if x0 <= row['pos'][0] < x0 + sx
                    and y0 <= row['pos'][1] < y0 + sy
                    and z0 <= row['pos'][2] < z0 + sz]
    protected_nearby = [row for row in support_rows if row.get('block_entity')
                        and x0 - margin <= row['pos'][0] < x0 + sx + margin
                        and z0 - margin <= row['pos'][2] < z0 + sz + margin]
    return {'clear': not unsupported and not obstructions and not protected_nearby,
            'supported': sx * sz - len(unsupported), 'footprint': sx * sz,
            'unsupported': unsupported, 'obstructions': obstructions,
            'protected_nearby': protected_nearby,
            'claim_status': 'unverified; the first placement must receive a server confirmation'}


def survey(client, origin, size):
    x, y, z = origin
    sx, sy, sz = size
    if sx < 1 or sy < 1 or sz < 1 or sx * sy * sz > 50000:
        raise ValueError('Worksite scan exceeds the native 50,000-block limit')
    support = client.request('scan', min=[x-3, y-1, z-3],
                             max=[x+sx+2, y+2, z+sz+2], details=True)['blocks']
    volume = client.request('scan', min=origin,
                            max=[x+sx-1, y+sy-1, z+sz-1], details=True)['blocks']
    return evaluate(origin, size, support, volume)


def main():
    p = argparse.ArgumentParser(description='Protected read-only projection site survey')
    p.add_argument('--origin', type=int, nargs=3, required=True)
    p.add_argument('--size', type=int, nargs=3, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--root', type=Path, default=Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation'))
    p.add_argument('--server', default='simpcraft.com:25565')
    a = p.parse_args()
    client = MaterialClient(a.root, a.output.parent / 'site-survey-session', server=a.server, record_experience=False)
    try:
        observed = survey(client, a.origin, a.size)
        record = {'origin': a.origin, 'size': a.size, 'server': a.server,
                  'world_session': client.world, 'observed': observed}
        a.output.parent.mkdir(parents=True, exist_ok=True)
        a.output.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(json.dumps({k: v for k, v in observed.items() if k not in ('obstructions', 'protected_nearby', 'unsupported')}, ensure_ascii=False))
    finally:
        client.finish()


if __name__ == '__main__':
    main()
