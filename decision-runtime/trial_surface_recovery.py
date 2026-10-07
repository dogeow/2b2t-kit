"""Bounded ordinary staircase ascent for a registered disposable trial.

Reuse the borer's existing-step/headroom idea through the trial SDK. Keep
solid neighbouring blocks as steps, clear only jump/body headroom, and let a
fresh World.paths graph authorize normal walking. This does not prove that
the player has reached the surface.
"""
from singleplayer_trial_bridge import Paused
from survival_world import cell, center, distance

MINEABLE = frozenset({'stone', 'andesite', 'diorite', 'granite', 'deepslate',
                      'tuff', 'calcite', 'dirt', 'grass_block'})
DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))
NEIGHBOURS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
              (0, -1, 0), (0, 0, 1), (0, 0, -1))
FALLING = frozenset({'sand', 'red_sand', 'gravel', 'suspicious_sand', 'suspicious_gravel',
                     'anvil', 'chipped_anvil', 'damaged_anvil', 'dragon_egg'})


def protected_cells(skills):
    protected = {tuple(point) for point in skills.stations.values()} | set(getattr(skills, 'excluded', ()))
    for key in skills.owned:
        values = key.split(',')
        if len(values) == 3 and all(value.lstrip('-').isdigit() for value in values):
            protected.add(tuple(map(int, values)))
    return protected


def _mineable(world, point, protected):
    if (point in protected or not world.safe(point) or world.name(point) not in MINEABLE
            or world.row(point).get('block_entity')):
        return False
    above = world.name((point[0], point[1] + 1, point[2]))
    if above in FALLING or above.endswith('_concrete_powder'):
        return False
    # A headroom excavation must not expose a currently observed liquid,
    # damaging block or unscanned neighbour. Falling blocks are not mineable.
    return all(world.safe(tuple(a + b for a, b in zip(point, delta))) for delta in NEIGHBOURS)


def _option(world, source, target, protected):
    support = (target[0], target[1] - 1, target[2])
    if (not world.stand(source) or not world.full(support) or support in protected
            or world.row(support).get('block_entity')):
        return None
    clearance = ((source[0], source[1] + 2, source[2]),
                 target, (target[0], target[1] + 1, target[2]))
    needed = []
    for point in clearance:
        if point in protected or not world.safe(point):
            return None
        if world.open(point):
            continue
        if not _mineable(world, point, protected):
            return None
        needed.append(point)
    return {'target': target, 'support': support, 'clearance': clearance,
            'needed': needed, 'support_state': world.row(support).get('state')}


def ascent_options(world, source, protected=()):
    """Only hypotheses: none of these coordinates is a cleared walk route."""
    protected = set(protected)
    options = []
    for dx, dz in DIRECTIONS:
        target = (source[0] + dx, source[1] + 1, source[2] + dz)
        option = _option(world, source, target, protected)
        if option is not None:
            options.append(option)
    return sorted(options, key=lambda option: (len(option['needed']), option['target']))


def plan_upward(world, state, protected=(), max_mined=8):
    """Pure candidate gate; cleared terrain must still be rescanned to walk."""
    actual = state.get('pos')
    if not isinstance(actual, (list, tuple)) or len(actual) != 3 or state.get('on_ground') is not True:
        return None
    source = cell(actual)
    if (abs(actual[1] - source[1]) > .2 or distance(actual, center(source)) > .25
            or not world.stand(source)):
        return None
    protected = set(protected) | {(source[0], source[1] - 1, source[2])}
    for option in ascent_options(world, source, protected):
        if (len(option['needed']) <= max_mined
                and (not option['needed'] or world.sight(source, option['needed'][0]))):
            return option
    return None


def _halt(skills, reason):
    skills.b.halted = True
    raise Paused(reason)


def recover_upward(skills, max_rises=4, max_mined=8):
    """Return actual bounded height progress; never claim surface completion.

    Unconfirmed mining/walking raises Paused and latches the existing bridge.
    Such a request is never resent by this recovery routine.
    """
    if (type(max_rises) is not int or not 1 <= max_rises <= 4
            or type(max_mined) is not int or not 0 <= max_mined <= 8):
        raise ValueError('Recovery is bounded to 4 rises and 8 mined blocks')
    if skills.b.halted or skills.b.pending_mutations:
        raise Paused('Unconfirmed native operation preserved; no staircase recovery')
    initial = list(skills.b.read()['pos'])
    mined, steps = 0, 0
    retained_supports = set()

    def result(reason):
        actual = list(skills.b.read()['pos'])
        rise = actual[1] - initial[1]
        return {'phase': 'progress' if rise >= .75 else 'blocked', 'reason': reason,
                'actual_rise': rise, 'mined': mined, 'steps': steps, 'position': actual,
                'surface_confirmed': False}

    for unused in range(max_rises):
        world = skills.scan()
        state = skills.b.read()
        actual = list(state['pos'])
        source = cell(actual)
        if (state.get('on_ground') is not True or abs(actual[1] - source[1]) > .2
                or not world.stand(source)):
            return result('Current supported standing pose is not verified')
        protected = protected_cells(skills) | retained_supports | {(source[0], source[1] - 1, source[2])}
        option = plan_upward(world, state, protected)
        if option is None:
            return result('No known safe existing step and mineable headroom')
        if mined + len(option['needed']) > max_mined:
            return result('Bounded mining budget cannot finish the next step')
        target, support = option['target'], option['support']
        source_support = (source[0], source[1] - 1, source[2])
        source_state = world.row(source_support).get('state')
        skills.event('surface_recovery_step_planned', target=list(target),
                     retained_support=list(support), mine_targets=[list(p) for p in option['needed']])
        for point in option['clearance']:
            if world.open(point):
                continue
            latest = skills.b.read()
            if (distance(latest['pos'], actual) > .3 or cell(latest['pos']) != source
                    or world.row(source_support).get('state') != source_state
                    or world.row(support).get('state') != option['support_state']
                    or _option(world, source, target, protected) is None
                    or not world.sight(source, point)):
                return result('Step headroom, footing or visible mining approach changed')
            receipt = skills.b.request('mine_block', pos=list(point),
                                       expected_state=world.row(point)['state'], seconds=18)
            if (receipt.get('phase') != 'done' or receipt.get('server_confirmed') is not True
                    or receipt.get('outcome_pending') is True):
                _halt(skills, 'Stair headroom excavation is unconfirmed; preserve request without replay')
            mined += 1
            world = skills.scan()
            if not world.open(point):
                _halt(skills, 'Confirmed stair headroom has no fresh open-cell evidence; no repeated excavation')
            skills.event('surface_recovery_headroom_confirmed', target=list(point),
                         request_id=receipt.get('id'), server_confirmed=True)
        latest = skills.b.read()
        if (distance(latest['pos'], actual) > .3
                or world.row(source_support).get('state') != source_state
                or world.row(support).get('state') != option['support_state']
                or not world.full(source_support) or not world.full(support)
                or not world.open((source[0], source[1] + 2, source[2]))):
            return result('Standing support or jump headroom changed before ascent')
        parents = world.paths(latest['pos'])
        if target not in parents:
            return result('Fresh normal walking graph does not contain the cleared step')
        route = world.route(parents, target)
        if len(route) > 2 or any(point not in {source, target} for point in route):
            return result('The cleared step lacks a direct normal one-block ascent')
        skills.walk(route)
        after = skills.b.read()
        if (after.get('on_ground') is not True or distance(after['pos'], center(target)) > .7
                or abs(after['pos'][1] - target[1]) > .2 or after['pos'][1] - actual[1] < .75):
            _halt(skills, 'Normal step arrival and actual height gain are unconfirmed; no walking replay')
        steps += 1
        retained_supports.update((source_support, support))
        skills.event('surface_recovery_ascent_confirmed', actual_position=list(after['pos']),
                     actual_rise=after['pos'][1] - initial[1], retained_support=list(support), flight_used=False)
    return result('Bounded ascent batch finished; surface remains unverified')
