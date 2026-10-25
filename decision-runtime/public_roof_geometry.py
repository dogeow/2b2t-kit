"""Choose a loaded, dry service-roof column for an explicitly supplied aisle.

Pure geometry only: returning a position never authorizes mining or movement.
The caller retains ownership, entity, health, quarantine and receipt checks.
"""


def choose_clear_roof(rows, origin_x, floor, aisle_z, blocked=(), *, low_x, high_x):
    if any(type(v) is not int for v in (origin_x, floor, aisle_z, low_x, high_x)) or low_x > high_x:
        raise ValueError('Explicit integer aisle coordinates and ordered bounds required')
    candidates=range(max(low_x, origin_x-2), min(high_x, origin_x+2)+1)
    for x in sorted(candidates,key=lambda value:abs(value-origin_x)):
        roof=(x,floor+3,aisle_z);base=rows.get((x,floor-1,aisle_z),{})
        if (roof in blocked or rows.get(roof,{}).get('state')!='Block{minecraft:dark_oak_planks}'
                or base.get('solid') is not True or base.get('fluid') is not False):continue
        if any((x,y,aisle_z) in rows for y in range(floor+4,floor+7)):continue
        body=[rows.get((x,y,aisle_z)) for y in range(floor,floor+3)]
        hazards=('minecraft:fire}','minecraft:soul_fire}','minecraft:cobweb}',
                 'minecraft:powder_snow}','minecraft:wall_torch}','minecraft:torch}')
        if any(row and (row.get('passable') is not True or row.get('fluid') is not False
                        or any(hazard in row.get('state','') for hazard in hazards)) for row in body):continue
        return list(roof)
    return None
