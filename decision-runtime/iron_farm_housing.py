"""Plan a conserved two-stage receive shaft above a verified empty bed room."""
import math


def walking_chute_plan(rows, *, room_min, room_max, floor_y, chute_x):
    """A fixed two-level path; its deep opening is covered before any cut."""
    if (len(room_min)!=2 or len(room_max)!=2 or room_max[0]-room_min[0]!=2
            or room_max[1]-room_min[1]!=2 or chute_x not in(room_min[0],room_max[0])):
        raise ValueError('One side column of a three-by-three bed room is required')
    middle=(room_min[0]+room_max[0])//2;free=room_max[0]if chute_x==room_min[0]else room_min[0]
    deep_z=room_min[1];entry_z=deep_z+1;ceiling_y=floor_y+4;deck_y=floor_y+5;temporary_y=floor_y+3
    ceiling=[[x,ceiling_y,z]for z in(deep_z,entry_z)for x in range(room_min[0],room_max[0]+1)]
    for x,_,z in ceiling:
        for y in(floor_y,ceiling_y,deck_y):
            if rows.get((x,y,z),{}).get('state')!='Block{minecraft:cobblestone}'or rows[x,y,z].get('fluid'):
                raise ValueError('Receiving floor, ceiling and deck must be intact dry cobblestone')
    cap=[chute_x,deck_y+1,deep_z]
    if rows.get(tuple(cap),{}).get('state')!='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]':
        raise ValueError('Install the full-width lower slab cap before opening the deep shaft')
    wall=room_min[0]-1 if chute_x==room_min[0]else room_max[0]+1
    if rows.get((wall,temporary_y,entry_z),{}).get('state')!='Block{minecraft:cobblestone}':
        raise ValueError('Catch floor must connect to an existing side wall')
    plates=[[chute_x,temporary_y,entry_z],[middle,temporary_y,entry_z]]
    if any(tuple(p)in rows for p in plates)or(chute_x,temporary_y,deep_z)in rows:
        raise ValueError('Receiving paths must be empty before placing temporary catch floors')
    return {'chute_x':chute_x,'middle_x':middle,'free_worker_x':free,'support_wall_x':wall,
            'cap':cap,'ceiling':ceiling,'platforms':plates,
            'deck_openings':[[chute_x,deck_y,deep_z],[chute_x,deck_y,entry_z],[middle,deck_y,entry_z]],
            'first_max_drop':2.5,'second_max_drop':3,'deep_opening_is_covered':True}


def receiving_plan(rows, villager, *, room_min, room_max, floor_y):
    if (villager.get('health') != 20 or villager.get('is_baby') is not False
            or len(room_min) != 2 or len(room_max) != 2
            or room_max[0] - room_min[0] != 2 or room_max[1] - room_min[1] != 2
            or type(floor_y) is not int):
        raise ValueError('One full-health adult and a verified three-by-three receiving room required')
    x, y, z = villager['pos']
    deck_y, ceiling_y, temporary_y = floor_y + 5, floor_y + 4, floor_y + 3
    if abs(y - (deck_y + 1)) > .05:
        raise ValueError('Villager must first be standing on the upper dry deck')
    columns = [[a, b] for a in range(math.floor(x - .31), math.floor(x + .31) + 1)
               for b in range(math.floor(z - .31), math.floor(z + .31) + 1)]
    if any(not room_min[0] <= a <= room_max[0] or not room_min[1] <= b <= room_max[1] for a, b in columns):
        raise ValueError('Villager footprint extends outside the prepared receiving room')
    for a in range(room_min[0], room_max[0] + 1):
        for b in range(room_min[1], room_max[1] + 1):
            for height in (floor_y, ceiling_y, deck_y):
                r = rows.get((a, height, b), {})
                if r.get('state') != 'Block{minecraft:cobblestone}' or r.get('fluid'):
                    raise ValueError('Continuous dry floor, ceiling and upper deck must remain intact before receiving')
            for height in (floor_y + 1, floor_y + 2, temporary_y):
                r = rows.get((a, height, b), {})
                if r and (r.get('fluid') or not ('minecraft:white_bed}' in r.get('state', '')
                                               or r.get('passable') is True)):
                    raise ValueError('Receiving room interior has an unplanned obstacle')
    free_x = room_max[0] if max(a for a, _ in columns) < room_max[0] else room_min[0]
    if any(a == free_x for a, _ in columns):
        raise ValueError('No separate worker column remains')
    direction = 1 if free_x == room_max[0] else -1
    wall_x = room_min[0] - 1 if direction == 1 else room_max[0] + 1
    end_x = max(a for a, _ in columns) if direction == 1 else min(a for a, _ in columns)
    platforms = [[a, temporary_y, b] for b in sorted({b for _, b in columns})
                 for a in range(wall_x + direction, end_x + direction, direction)]
    for b in {b for _, b in columns}:
        if rows.get((wall_x, temporary_y, b), {}).get('state') != 'Block{minecraft:cobblestone}':
            raise ValueError('Temporary platform has no existing side-wall support')
    return {'columns': columns, 'free_worker_x': free_x, 'support_wall_x': wall_x, 'platforms': platforms,
            'floor_y': floor_y, 'ceiling_y': ceiling_y, 'deck_y': deck_y, 'temporary_y': temporary_y,
            'first_max_drop': deck_y + 1 - (temporary_y + 1),
            'second_max_drop': temporary_y + 1 - (floor_y + 1)}
