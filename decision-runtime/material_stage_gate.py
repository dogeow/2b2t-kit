"""Require fresh complete material evidence before advancing a build stage."""


def require_gravel_complete(audit, state, target, expected_chests,
                            max_age_ms=15 * 60 * 1000):
    if target < 1 or not expected_chests:
        raise ValueError('A positive target and expected chest list are required')
    if (audit.get('server') != state.get('server') or
            audit.get('dimension') != state.get('dimension') or
            audit.get('world_session') != state.get('world_session')):
        raise RuntimeError('Material audit belongs to another world or session')
    age = state.get('time', 0) - audit.get('at_ms', 0)
    if age < 0 or age > max_age_ms:
        raise RuntimeError('Material audit is missing or stale')
    by_pos = {tuple(chest.get('pos', [])): chest for chest in audit.get('chests', [])}
    if any(tuple(pos) not in by_pos or 'items' not in by_pos[tuple(pos)]
           for pos in expected_chests):
        raise RuntimeError('Not every required chest was audited cleanly')
    stored = sum(by_pos[tuple(pos)]['items'].get('minecraft:gravel', 0)
                 for pos in expected_chests)
    carried = audit.get('carried_gravel')
    if not isinstance(carried, int) or carried < 0:
        raise RuntimeError('Audit did not record carried gravel')
    total = stored + carried
    if total < target:
        raise RuntimeError(f'Gravel collection incomplete: {total} of {target}')
    return {'stored': stored, 'carried_at_audit': carried,
            'total_at_audit': total, 'target': target,
            'audit_age_ms': age}
