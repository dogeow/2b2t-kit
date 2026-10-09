"""Keep explicitly registered map-transparent lights out of image-cell accounting."""

from lighting_cli import EVIDENCE


def matching_map_support(row, expected, image_y, require_dark=True):
    """Only an exact current pixel in the caller's verified immutable model."""
    if not isinstance(row,dict):
        return False
    pos=row.get('pos')
    if (not isinstance(pos,list) or len(pos)!=3 or any(type(v)is not int for v in pos)
            or pos[1]!=image_y or not isinstance(expected,dict)):
        return False
    goal=expected.get(tuple(pos))
    state=goal.get('state') if isinstance(goal,dict) else goal
    return bool(isinstance(state,str) and state!='Block{minecraft:air}' and row.get('state')==state
        and row.get('solid')is True and row.get('fluid')is False and row.get('block_entity')is False
        and row.get('zombie_spawn_floor')is True
        and type(row.get('spawn_block_light'))is int and 0<=row['spawn_block_light']<=15
        and type(row.get('monster_spawn_block_light_limit'))is int and 0<=row['monster_spawn_block_light_limit']<=15
        and (not require_dark or row.get('zombie_block_light_risk')is True
             and row['spawn_block_light']<=row['monster_spawn_block_light_limit']))


def completed_map_light_positions(reports, world, image_y):
    """Accept only completed current-world normal standing-torch placements."""
    positions = set()
    for report in reports:
        if (not isinstance(report, dict) or report.get('world_session') != world
                or report.get('park_native_confirmed') is not True
                or report.get('state') != 'bounded_run_finished'
                or not isinstance(report.get('placed'), list)):
            raise ValueError('Completed current-world lighting report required')
        for row in report['placed']:
            if not isinstance(row, dict):
                raise ValueError('Standing-torch placement record required')
            pos = row.get('target')
            before, after = row.get('before_stock'), row.get('after_stock')
            if (not isinstance(pos, list) or len(pos) != 3
                    or any(type(v) is not int for v in pos) or pos[1] != image_y + 1
                    or row.get('world_session') != world or row.get('state') != 'verified'
                    or row.get('later_verified_frames') != 2
                    or row.get('observed_block_state') != 'Block{minecraft:torch}'
                    or row.get('evidence_scope') != EVIDENCE
                    or not isinstance(row.get('interaction_request'), str)
                    or not row['interaction_request'] or not row.get('task_session')
                    or type(before) is not int or type(after) is not int
                    or after < 0 or before - after != 1
                    or tuple(pos) in positions):
                raise ValueError('Distinct exact standing-torch placement evidence required')
            positions.add(tuple(pos))
    return frozenset(positions)


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
