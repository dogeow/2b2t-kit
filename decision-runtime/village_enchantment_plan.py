"""Plan one requested maximum book per main-hall cell, preserving known locks."""
from copy import deepcopy


def bind_required_books(layout, targets, locked):
    """Only changes desired roles; never manufactures a trade or game receipt."""
    slots = layout.get('slots', [])
    if (not isinstance(targets, dict) or len(targets) != len(slots)
            or any(not isinstance(e, str) or not e.startswith('minecraft:')
                   or type(level) is not int or level < 1 for e, level in targets.items())):
        raise ValueError('One physical main-hall cell per requested maximum book required')
    ids = [v['id'] for v in slots]
    occupants = [v['occupant_uuid'] for v in slots if v.get('occupant_uuid')]
    if len(set(ids)) != len(ids) or len(set(occupants)) != len(occupants):
        raise ValueError('Ambiguous main-hall cell or resident')
    result = deepcopy(layout)
    by_uuid = {v['occupant_uuid']: v for v in result['slots'] if v.get('occupant_uuid')}
    by_slot, assigned, changes = {}, set(), []
    for enchantment, record in locked.items():
        uid = record.get('villager_uuid')
        if (enchantment not in targets or record.get('level') != targets[enchantment]
                or not isinstance(record.get('proof'), str) or not record['proof']
                or uid not in by_uuid or by_uuid[uid]['id'] in by_slot):
            raise ValueError('Known lock must match one current resident and requested maximum')
        by_slot[by_uuid[uid]['id']] = enchantment
        assigned.add(enchantment)
    for row in result['slots']:
        role = row.get('role', {})
        e = role.get('enchantment')
        if row['id'] not in by_slot and (role.get('kind') == 'librarian'
                and e in targets and role.get('level') == targets[e] and e not in assigned):
            by_slot[row['id']] = e
            assigned.add(e)
    missing = iter(e for e in targets if e not in assigned)
    for row in result['slots']:
        e = by_slot.get(row['id'])
        if e is None:
            e = next(missing)
        before = deepcopy(row.get('role'))
        role = dict(before or {}) if (before or {}).get('enchantment') == e else {}
        role.update(kind='librarian', block='minecraft:lectern', enchantment=e,
                    level=targets[e], max_only=True)
        row['role'] = role
        if before != role:
            changes.append(dict(slot=row['id'], before=before, after=deepcopy(role)))
    actual = {v['role']['enchantment']: v['role']['level'] for v in result['slots']}
    if actual != targets:
        raise RuntimeError('Book role plan omitted or duplicated a requirement')
    result.update(counter_target=len(slots), librarian_target=len(targets),
                  other_profession_target=0, book_role_plan_only=True)
    return result, changes
