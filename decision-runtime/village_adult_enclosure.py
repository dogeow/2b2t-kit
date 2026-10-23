"""Conservative standing-adult containment from loaded boundary columns.

Only witnessed full horizontal collision layers count. Unknown shapes count as
open space. This is a physical enclosure audit, never reset or mining authority.
"""
from projection_completion import block_state


def layers(row):
    if not row or row.get('fluid') is not False:
        return []
    try:
        kind, props = block_state(row.get('state', 'Block{minecraft:air}'))
    except (ValueError, TypeError):
        return []
    if row.get('solid') is True and row.get('block_entity') is False:
        return [(0., 1.)]
    if props.get('waterlogged') != 'false':
        return []
    if kind.endswith('_slab'):
        return {'bottom': [(0., .5)], 'top': [(.5, 1.)],
                'double': [(0., 1.)]}.get(props.get('type'), [])
    if kind.endswith('_trapdoor') and props.get('open') == 'false':
        return {'bottom': [(0., .1875)], 'top': [(.8125, 1.)]}.get(props.get('half'), [])
    return []


def maximum_gap(intervals, low, high):
    cursor = low
    longest = 0.
    for start, end in sorted(intervals):
        start, end = max(low, start), min(high, end)
        if end <= cursor:
            continue
        longest = max(longest, start - cursor)
        cursor = max(cursor, end)
    return max(longest, high - cursor)


def audit(rows, *, front, floor, inward, depth):
    """An entire perimeter must have no standing-adult aperture >= 1.9 blocks.

    Every interior floor and roof is independently checked. The highest observed
    roof underside is used for ALL boundary columns, conservatively. Explicit
    geometry is required; a resident staying inside is not containment proof.
    """
    if (len(front) != 3 or any(type(v) is not int for v in front)
            or type(floor) is not int or front[1] != floor
            or type(inward) is not int or inward not in (-1, 1)
            or type(depth) is not int or depth not in (2, 3, 4)):
        raise ValueError('Explicit integer floor, front, direction and bounded depth required')
    x, _, z = front
    interior = [z + n * inward for n in range(1, depth + 1)]
    issues = []
    ceilings = []
    for zz in [z, *interior]:
        if layers(rows.get((x, floor - 1, zz))) != [(0., 1.)]:
            issues.append({'pos': [x, floor - 1, zz], 'reason': 'full_dry_floor_missing'})
    for zz in interior:
        pos = (x, floor + 3, zz)
        supported = layers(rows.get(pos))
        if not supported:
            issues.append({'pos': list(pos), 'reason': 'continuous_dry_roof_layer_missing'})
        else:
            ceilings.append(floor + 3 + supported[0][0])
    # Missing roof evidence cannot be replaced with a guessed ceiling.
    if len(ceilings) != depth:
        return {'verified': False, 'issues': issues, 'boundary_columns': []}
    high = max(ceilings)
    perimeter = [(x, z), (x, z + (depth + 1) * inward)]
    perimeter += [(xx, zz) for zz in interior for xx in (x - 1, x + 1)]
    columns = []
    for xx, zz in perimeter:
        intervals = [(yy + lo, yy + hi)
                     for yy in range(floor, floor + 5)
                     for lo, hi in layers(rows.get((xx, yy, zz)))]
        gap = maximum_gap(intervals, float(floor), high)
        columns.append({'xz': [xx, zz], 'maximum_open_height': gap})
        if gap >= 1.9:
            issues.append({'xz': [xx, zz], 'reason': 'standing_adult_aperture_not_closed',
                           'maximum_open_height': gap})
    return {'verified': not issues, 'issues': issues, 'boundary_columns': columns,
            'ceiling_upper_bound': high, 'minimum_standing_adult_height': 1.9,
            'interior_depth': depth, 'front': front, 'floor': floor,
            'scope': 'standing_adult_physical_enclosure_not_reset_authority'}
