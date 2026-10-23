"""Prove an adult cannot leave a cell while its untraded lectern is reset."""
from projection_completion import block_state

FULL_CUBES = frozenset('minecraft:' + name for name in (
    'dark_oak_planks', 'cherry_planks', 'oak_planks', 'cobblestone',
    'stone', 'dirt', 'grass_block',
))


def require_enclosed_reset(scene, room):
    """Geometry only: native ownership, quote and duplicate guards remain required.

    Standing on a bed is valid. The actual adult body, closed window, complete
    shell and unoccupied placement target provide the containment evidence.
    """
    rows = {tuple(v['pos']): v for v in scene['blocks']}
    room.require_caps(rows)
    actor = room.actor(scene)
    x, y, z = room.work
    floor = room.floor_y
    if y != floor:
        raise ValueError('Raised workpoints need their separately verified reset route')
    kind, props = block_state(rows[(x, y + 1, z)]['state'])
    if kind.endswith('_slab') and props.get('type') == 'bottom' and props.get('waterlogged') == 'false':
        opening = 1.0
        pickup = 'public_front_only'
    elif (kind.endswith('_trapdoor') and props.get('half') == 'top'
          and props.get('open') == 'false' and props.get('waterlogged') == 'false'):
        opening = 1.8125
        pickup = 'public_front_then_empty_workpoint'
    else:
        raise ValueError('Reset needs an actually closed verified counter window')

    def full(pos):
        row = rows.get(pos, {})
        name, _ = block_state(row.get('state', 'Block{minecraft:air}'))
        if (name not in FULL_CUBES or row.get('solid') is not True
                or row.get('fluid') is not False or row.get('block_entity') is not False):
            raise ValueError('Reset cell shell or floor is not a witnessed full cube')

    if type(room.interior_depth)is not int or room.interior_depth not in (2,3):
        raise ValueError('Only explicit two or three cell interiors are supported')
    interior = [z + n * room.inward for n in range(1, room.interior_depth+1)]
    for zz in interior:
        full((x, floor - 1, zz))
        full((x, floor + 3, zz))
        for yy in range(floor, floor + 3):
            full((x - 1, yy, zz))
            full((x + 1, yy, zz))
    for yy in range(floor, floor + 3):
        full((x, yy, z + (room.interior_depth+1) * room.inward))
    full((x, floor - 1, z))
    full((x, floor + 2, z))
    box = actor['bounds']
    low, high = box['min'], box['max']
    height = high[1] - low[1]
    if (height < 1.9 or height <= opening
            or low[0] < x - 1e-6 or high[0] > x + 1 + 1e-6
            or low[2] < min(interior) - 1e-6 or high[2] > max(interior) + 1 + 1e-6
            or low[1] < floor - .01 or high[1] > floor + 3 + .01):
        raise ValueError('Actual adult body is not inside the verified enclosure')
    for entity in scene['scan_entities']:
        bounds = entity['bounds']
        if all(bounds['max'][i] > room.work[i] and bounds['min'][i] < room.work[i] + 1
               for i in range(3)):
            raise ValueError('Reset workpoint is occupied by an entity')
    return {'scan_time': scene['time'], 'world_session': scene['world_session'],
            'villager_uuid': room.uid, 'adult_height': height,
            'counter_opening': opening, 'pickup_route': pickup, 'interior_depth':room.interior_depth,
            'standing_on_bed_allowed': True, 'complete_shell_verified': True}
