"""Replenish actual bow ammunition through the existing material controller."""
from pathlib import Path
from kit_runtime.journal import write_json

ARROWS = frozenset(('minecraft:arrow', 'minecraft:tipped_arrow', 'minecraft:spectral_arrow'))


def ammunition_target(state):
    """Absolute normal-arrow target, or zero when carried ammunition is ready."""
    rows = [r for r in state.get('inventory', [])
            if type(r.get('slot')) is int and (0 <= r['slot'] < 36 or r['slot'] == 40)
            and type(r.get('count')) is int and r['count'] > 0]
    bows = [r for r in rows if r.get('item') == 'minecraft:bow'
            and type(r.get('durability')) is int and r['durability'] >= 32]
    if not bows:
        return 0
    normal = sum(r['count'] for r in rows if r.get('item') == 'minecraft:arrow')
    infinite = any(any(e.get('id') == 'minecraft:infinity'
                       and type(e.get('level')) is int and e['level'] > 0
                       for e in r.get('enchantments', [])) for r in bows)
    if infinite:
        return 0 if normal else 1
    total = sum(r['count'] for r in rows if r.get('item') in ARROWS)
    return 0 if total >= 16 else normal + 16 - total


def prepare(backend, out, initial=None):
    """Keep ordinary supply permissions, menu ownership and safety gates intact."""
    before = initial if initial is not None else backend.ensure_client().status()
    target = ammunition_target(before)
    if not target:
        return {'phase': 'done', 'detail': '当前携带弓的箭储备无需补充'}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    receipt = backend.fetch({'minecraft:arrow': target})
    after = backend.ensure_client().status()
    ready = ammunition_target(after) == 0
    proof = {'world_session': after.get('world_session'), 'target': target,
             'supply_receipt': receipt, 'observed_at': after.get('time'),
             'actual_ammunition_ready': ready, 'inventory_credit_from_records': 0}
    write_json(out / 'bow-ammunition.json', proof)
    if ready:
        return {'phase': 'done', 'detail': '已核对真实背包中的弓箭储备'}
    return {'phase': 'waiting', 'code': 'WAIT_COMBAT_EQUIPMENT',
            'detail': '携带的弓缺少可用箭，先补齐远程防护物资再潜水',
            'requirements': {'minecraft:arrow': ammunition_target(after)}}
