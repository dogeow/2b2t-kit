"""Keep explicitly registered map-transparent lights out of image-cell accounting."""


def registered_map_light(row, expected, observed, registered_positions, image_y):
    pos = row.get('pos')
    if (not isinstance(pos, list) or len(pos) != 3
            or any(type(n) is not int for n in pos)
            or tuple(pos) not in registered_positions or pos[1] != image_y + 1
            or row.get('state') != 'Block{minecraft:torch}'
            or row.get('passable') is not True or row.get('solid') is not False
            or row.get('fluid') is not False or row.get('block_entity') is not False):
        return False
    base = (pos[0], image_y, pos[2])
    goal, actual = expected.get(base), observed.get(base)
    return bool(isinstance(goal, dict) and isinstance(actual, dict)
                and actual.get('state') == goal.get('state')
                and isinstance(goal.get('state'), str)
                and goal['state'] != 'Block{minecraft:air}'
                and actual.get('solid') is True
                and actual.get('fluid') is False
                and actual.get('block_entity') is False)
