"""Bind each sleeper to its current observed bed, never an old assigned bed."""
import math
from village_beds import DELTAS, matches


def current_claims(scene, flags, expected_uuids, *, include_babies=False):
    """Return all witnessed claims, or None while any resident is awake/unseen."""
    if (type(include_babies) is not bool
            or not isinstance(expected_uuids, (set, frozenset)) or not expected_uuids
            or not isinstance(flags, dict) or not scene.get('world_session')
            or scene['world_session'] != flags.get('world_session')
            or type(scene.get('time')) is not int or type(flags.get('time')) is not int
            or abs(scene['time'] - flags['time']) > 1000
            or not scene.get('scan_total_cells')
            or scene.get('scan_cells_read') != scene['scan_total_cells']):
        raise ValueError('Complete same-world fresh sleeping-bed observations required')
    actors = [v for v in scene.get('scan_entities', []) if v.get('type') == 'minecraft:villager']
    observations = flags.get('villagers', [])
    if (len({v['uuid'] for v in actors}) != len(actors)
            or len({v['uuid'] for v in observations}) != len(observations)):
        raise ValueError('Duplicate villager observation')
    by_id = {v['uuid']: v for v in actors}
    by_flag = {v['uuid']: v for v in observations}
    blocks = {tuple(v['pos']): v for v in scene.get('blocks', [])}
    claims, claimed_heads = {}, set()
    for uid in sorted(expected_uuids):
        v, flag = by_id.get(uid), by_flag.get(uid)
        if not v or not flag or flag.get('sleeping') is not True:
            return None
        if (v.get('alive') is not True or v.get('health') != 20
                or type(v.get('is_baby')) is not bool
                or flag.get('is_baby') is not v['is_baby']
                or v['is_baby'] and not include_babies
                or flag.get('passenger') is not False or flag.get('no_ai_client_flag') is not False
                or type(v.get('id')) is not int or v['id'] != flag.get('entity_id')):
            raise ValueError('Sleeping resident identity or health is unverified')
        p = flag.get('sleeping_pos')
        if (not isinstance(p, list) or len(p) != 3
                or any(type(n) not in (int, float) or not math.isfinite(n) or int(n) != n for n in p)):
            raise ValueError('Actual sleeping position is unavailable')
        head = tuple(int(n) for n in p)
        if head in claimed_heads or tuple(math.floor(n) for n in v['pos']) != head:
            raise ValueError('Sleeping bed ownership is ambiguous')
        state = blocks.get(head, {}).get('state', '')
        facing = next((d for d in DELTAS if 'facing=' + d in state), None)
        if facing is None:
            raise ValueError('Actual bed head is unobserved')
        foot = tuple(head[i] - DELTAS[facing][i] for i in range(3))
        if (not matches(blocks.get(head), 'minecraft:white_bed', 'head', facing)
                or not matches(blocks.get(foot), 'minecraft:white_bed', 'foot', facing)
                or any('occupied=true' not in blocks[cell]['state'] for cell in (head, foot))):
            raise ValueError('Both occupied halves of the actual bed are required')
        claims[uid] = dict(head=list(head), foot=list(foot), facing=facing,
                           entity_id=v['id'], head_state=state, foot_state=blocks[foot]['state'])
        claimed_heads.add(head)
    return claims
