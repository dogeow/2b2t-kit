"""One native AutoChopper batch for the exact disposable trial.

This adapter does not mine individual logs or pretend to bind a fixed tree.
The current host chooses its nearest natural tree of the surveyed species.
Worker receipts preserve the actual native status frame outside its mailbox.
"""
import json
import math
import re
import uuid
from pathlib import Path

from survival_bridge import Paused, inventory
from survival_world import cell

LOG_IDS = frozenset('minecraft:' + name + '_log' for name in
                   ('oak', 'spruce', 'birch', 'jungle', 'acacia', 'dark_oak',
                    'mangrove', 'cherry', 'pale_oak'))
SUPPORTED_HOSTS = frozenset({'2026.10.7.6'})
RECEIPT_SCHEMA = 1
RECEIPT_SOURCE = 'matched_native_status_snapshot'
NATIVE_TREE_REACH_XZ = 32 + 79 + 8  # search + <=80 connected logs + crown bounds
_SAFE_ID = re.compile(r'trial-[A-Za-z0-9_-]{1,74}\Z')


def supports_native_chop(state):
    # .5 advertises fixed_tree_chop_protocol too, but cannot coordinate Flight
    # or clean up this run's child. Do not infer trial support from that field.
    return (state.get('kit_version') in SUPPORTED_HOSTS
            and state.get('tree_survey_protocol') == 1
            and state.get('singleplayer_trial_protocol') == 1)


def complete_tree_survey(result, arguments, expected_revision, origin):
    """Positive loaded-tree evidence; omitted/unloaded cells never mean air."""
    radius, item = arguments.get('radius', 64), arguments.get('item')
    if (item not in LOG_IDS or type(radius) is not int or not 8 <= radius <= 96
            or result.get('tree_survey_protocol') != 1
            or type(result.get('control_revision')) is not int
            or result['control_revision'] != expected_revision
            or not isinstance(origin, (list, tuple)) or len(origin) != 3
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in origin)):
        return False
    survey = result.get('tree_survey')
    if not isinstance(survey, dict):
        return False
    loaded, missing = survey.get('loaded_columns'), survey.get('unloaded_columns')
    trees, surface = survey.get('trees'), survey.get('highest_surface')
    if (type(loaded) is not int or type(missing) is not int or min(loaded, missing) < 0
            or loaded + missing != (2 * radius + 1) ** 2
            or type(surface) is not int or not -64 <= surface <= 320
            or not isinstance(trees, list) or len(trees) > 128
            or not isinstance(survey.get('biomes'), dict)):
        return False
    seen = set()
    ox, _, oz = cell(origin)
    for tree in trees:
        if not isinstance(tree, dict):
            return False
        point, leaves, top = tree.get('pos'), tree.get('natural_leaves'), tree.get('top')
        if (not isinstance(point, list) or len(point) != 3
                or any(type(n) is not int for n in point)
                or not -64 <= point[1] <= 319
                or abs(point[0] - ox) > radius or abs(point[2] - oz) > radius
                or type(leaves) is not int or not 4 <= leaves <= 1519
                or type(top) is not int or not point[1] < top <= 320
                or point[1] < top - 48 or tuple(point) in seen):
            return False
        seen.add(tuple(point))
    return True


def validate_chop_arguments(state, arguments):
    if not supports_native_chop(state):
        raise Paused('This host has no verified native trial chopper coordination')
    if (state.get('dimension') != 'minecraft:overworld' or state.get('on_ground') is not True
            or state.get('under_water') is True or state.get('screen', '')
            or any(state.get(key) for key in ('chopping', 'navigating', 'borer_active', 'printing'))):
        raise Paused('Native trial chopping needs grounded idle Overworld control')
    if (arguments.get('item') not in LOG_IDS
            or type(arguments.get('target_count')) is not int
            or not 1 <= arguments['target_count'] <= 512
            or type(arguments.get('tree_limit')) is not int or arguments['tree_limit'] != 1
            or type(arguments.get('seconds')) is not int or not 30 <= arguments['seconds'] <= 300
            or set(arguments) - {'item', 'target_count', 'tree_limit', 'seconds'}):
        raise Paused('Trial chopper requires one bounded ordinary natural-tree batch')
    if arguments['target_count'] <= inventory(state).get(arguments['item'].removeprefix('minecraft:'), 0):
        raise Paused('Native log inventory target is already satisfied; no tree dispatched')
    # A whole natural tree can overshoot by up to 80 logs. Leave room for two
    # log stacks and its other drops; partial inventory lists cannot prove room.
    rows = state.get('inventory', [])
    slots = {row.get('slot'): row for row in rows if isinstance(row, dict)
             and type(row.get('slot')) is int and 0 <= row['slot'] < 36}
    if (set(slots) != set(range(36))
            or sum(row.get('item') == 'minecraft:air' and row.get('count') == 0
                   for row in slots.values()) < 4):
        raise Paused('Whole-tree pickup needs four freshly observed empty inventory slots')


def _idle_chop_terminal(state):
    keys = state.get('movement_keys')
    return (state.get('phase') == 'done' and state.get('op') == 'chop'
            and state.get('chopping') is False
            and state.get('outcome_pending') is not True
            and type(state.get('chopper_remaining')) is int and state['chopper_remaining'] == 0
            and type(state.get('chopper_platforms')) is int and state['chopper_platforms'] == 0
            and type(state.get('chopper_verified_trees')) is int and state['chopper_verified_trees'] >= 1
            and state.get('on_ground') is True and state.get('manual_movement') is False
            and state.get('screen', '') == ''
            and isinstance(keys, dict) and {'forward', 'back', 'jump', 'sneak'} <= keys.keys()
            and all(value is False for value in keys.values()))


def _same_scope(frame, request):
    identity = frame.get('trial_identity', {})
    return (frame.get('connected') is True and frame.get('server') == 'singleplayer'
            and frame.get('game_mode') == 'survival'
            and frame.get('singleplayer_trial_protocol') == 1
            and frame.get('world_id') == request.get('world_id')
            and frame.get('world_session') == request.get('world_session')
            and frame.get('dimension') == request.get('dimension')
            and identity.get('registered') is True
            and identity.get('world_id') == request.get('world_id')
            and identity.get('trial_id') == request.get('trial_id')
            and identity.get('run_id') == request.get('run_id')
            and type(frame.get('time')) is int
            and frame.get('manual_movement') is False)


def _counts(frame):
    rows = frame.get('inventory')
    if not isinstance(rows, list) or len(rows) > 128:
        return None
    result = {}
    for row in rows:
        if (not isinstance(row, dict) or not isinstance(row.get('item'), str)
                or not row['item'].startswith('minecraft:') or type(row.get('count')) is not int
                or not 0 <= row['count'] <= 999):
            return None
        result[row['item']] = result.get(row['item'], 0) + row['count']
    return result


def _valid_ledger(value, request_id=None):
    if not isinstance(value, dict) or value.get('schema') != RECEIPT_SCHEMA or value.get('source') != RECEIPT_SOURCE:
        return False
    request, before, result = value.get('request'), value.get('before'), value.get('native_result')
    if not all(isinstance(part, dict) for part in (request, before, result)):
        return False
    rid = request.get('id')
    if (not isinstance(rid, str) or not _SAFE_ID.fullmatch(rid) or request_id not in (None, rid)
            or request.get('op') != 'chop' or request.get('local_trial') is not True
            or request.get('local_survival') is not True
            or not _same_scope(before, request) or not _same_scope(result, request)
            or not supports_native_chop(before) or not supports_native_chop(result)
            or result.get('id') != rid or result.get('last_request') != rid
            or type(request.get('expected_revision')) is not int
            or before.get('control_revision') != request['expected_revision']
            or result.get('control_revision') != request['expected_revision'] + 1
            or result['time'] < before['time'] or not _idle_chop_terminal(result)):
        return False
    arguments = {key: request.get(key) for key in ('item', 'target_count', 'tree_limit', 'seconds')}
    try:
        validate_chop_arguments(before, arguments)
    except (Paused, KeyError, TypeError):
        return False
    first, last = _counts(before), _counts(result)
    if first is None or last is None:
        return False
    gain = last.get(request['item'], 0) - first.get(request['item'], 0)
    return (0 <= gain <= 80 and all(type(value.get(key)) is int for key in ('before_count', 'after_count', 'gained'))
            and value.get('before_count') == first.get(request['item'], 0)
            and value.get('after_count') == last.get(request['item'], 0)
            and value.get('gained') == gain)


def _receipt_root(automation):
    return Path(automation).resolve().parent / 'singleplayer-trial/worker/native-chop-receipts'


def record_chop_receipt(automation, request, before, native_result):
    """Copy matched native status proof; never write a host reply or new action."""
    first, last = _counts(before), _counts(native_result)
    if first is None or last is None:
        raise Paused('Native chop inventory observation is malformed; keep its intent pending')
    item = request.get('item')
    value = {'schema': RECEIPT_SCHEMA, 'source': RECEIPT_SOURCE,
             'request': request, 'before': before, 'native_result': native_result,
             'before_count': first.get(item, 0), 'after_count': last.get(item, 0),
             'gained': last.get(item, 0) - first.get(item, 0)}
    if not _valid_ledger(value):
        raise Paused('Native chop termination or exact ownership is unconfirmed; keep its intent pending')
    root = _receipt_root(automation)
    if any(parent.is_symlink() for parent in (root, *root.parents)):
        raise Paused('Native chop receipt directory must not contain symlinks')
    root.mkdir(parents=True, exist_ok=True)
    path = root / (request['id'] + '.json')
    if path.exists():
        if path.is_symlink() or json.loads(path.read_text()) != value:
            raise Paused('A different native chop receipt exists; preserve it')
        return value
    temp = root / (request['id'] + '.' + uuid.uuid4().hex[:8] + '.tmp')
    temp.write_text(json.dumps(value, allow_nan=False, ensure_ascii=False) + '\n')
    temp.replace(path)
    return value


def known_chop_receipt(game, registry, unresolved, state=None):
    """Hot-update helper: return exact already observed terminal proof or None.

    Call only for an unresolved ``op=chop`` entry; no absence/timeout is proof.
    This accepts a copied native frame, not a fabricated automation reply.
    """
    rid = unresolved.get('id')
    if unresolved.get('op') != 'chop' or not isinstance(rid, str) or not _SAFE_ID.fullmatch(rid):
        return None
    root = _receipt_root(Path(game) / 'config/twob2tkit/automation')
    path = root / (rid + '.json')
    try:
        if any(parent.is_symlink() for parent in (path, *path.parents)) or not path.is_file() or path.stat().st_size > 2_000_000:
            return None
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not _valid_ledger(value, rid):
        return None
    request = value['request']
    expected_run = unresolved.get('run_id', registry.get('run_id'))
    if (request.get('world_id') != registry.get('world_id')
            or request.get('trial_id') != registry.get('trial_id')
            or request.get('run_id') != expected_run
            or request.get('world_session') != unresolved.get('world_session')):
        return None
    if any(key in unresolved and unresolved[key] != request.get(key)
           for key in ('world_id', 'trial_id', 'run_id', 'dimension')):
        return None
    current_scope = {**request, 'run_id': registry.get('run_id')}
    if state is not None and (not _same_scope(state, current_scope)
            or state['time'] < value['native_result']['time']
            or type(state.get('control_revision')) is not int
            or state['control_revision'] < value['native_result']['control_revision']):
        return None
    return value


def native_chop_protection_clear(skills, state, world):
    """Guard the real free selector, not merely the Python candidate root.

    .6 searches at most 32 blocks, floods up to 80 touching logs and adds an
    8-block canopy bounding margin. A square bound is intentionally broader
    than the circular search. Owned stations and soil supports are not wood.
    """
    origin = cell(state['pos'])
    def intersects(point, margin=0):
        return (isinstance(point, (tuple, list)) and len(point) == 3
                and all(type(n) is int for n in point)
                and abs(point[0]-origin[0]) <= NATIVE_TREE_REACH_XZ + margin
                and abs(point[2]-origin[2]) <= NATIVE_TREE_REACH_XZ + margin)
    camp = getattr(skills, 'camp', None)
    if camp is not None:
        if (not isinstance(camp, (list, tuple)) or len(camp) != 3
                or any(type(n) is not int for n in camp) or intersects(camp, 3)):
            return False
    def wood(name):
        return isinstance(name, str) and name.removeprefix('minecraft:').endswith(('_log', '_wood', '_stem', '_hyphae'))
    for key, name in getattr(skills, 'owned', {}).items():
        if not wood(name):
            continue
        try:
            point = tuple(int(part) for part in key.split(','))
        except (TypeError, ValueError, AttributeError):
            return False  # A malformed owned-wood coordinate cannot be ignored.
        if len(point) != 3 or intersects(point):
            return False
    return not any(intersects(point) and wood(world.name(tuple(point)))
                   for point in getattr(skills, 'excluded', set()))


def observed_chop_plan(skills, state, world, target_logs=4):
    """A local candidate species; the native survey still checks real trees."""
    if (type(target_logs) is not int or not 1 <= target_logs <= 64
            or not supports_native_chop(state) or state.get('on_ground') is not True
            or state.get('under_water') is True or state.get('screen', '')
            or any(state.get(key) for key in ('chopping', 'navigating', 'borer_active', 'printing'))):
        return None
    if not native_chop_protection_clear(skills, state, world):
        return None
    stock = inventory(state)
    total = sum(stock.get(item.removeprefix('minecraft:'), 0) for item in LOG_IDS)
    if total >= target_logs:
        return None
    protected = set(getattr(skills, 'excluded', set()))
    protected.update(tuple(p) for p in getattr(skills, 'stations', {}).values())
    camp = getattr(skills, 'camp', None)
    rows = []
    for point, row in world.blocks.items():
        item = 'minecraft:' + world.name(point)
        if (item not in LOG_IDS or point in protected or row.get('block_entity')
                or not world.earth((point[0], point[1] - 1, point[2]))
                or abs(point[0] - math.floor(state['pos'][0])) > 8
                or abs(point[2] - math.floor(state['pos'][2])) > 8
                or camp and abs(point[0] - camp[0]) <= 3 and abs(point[2] - camp[2]) <= 3):
            continue
        rows.append((math.dist(state['pos'], point), point, item))
    if not rows:
        return None
    _, root, item = min(rows)
    if stock.get('dirt', 0) < 1 and not world.resource(state['pos'], {'dirt', 'grass_block'}, protected):
        return None
    return {'item': item, 'observed_root': list(root), 'radius': 8,
            'target_count': stock.get(item.removeprefix('minecraft:'), 0) + target_logs - total,
            'target_logs': target_logs, 'support_needed': max(0, 1 - stock.get('dirt', 0))}


def gather_native_wood(skills, target_logs=4):
    """Dispatch at most one native tree; inventory, not timer, proves progress."""
    skills.check()
    if type(target_logs) is not int or not 1 <= target_logs <= 64:
        raise Paused('Trial wood target must be 1..64 carried logs')
    before = skills.b.read()
    stock = inventory(before)
    if sum(stock.get(item.removeprefix('minecraft:'), 0) for item in LOG_IDS) >= target_logs:
        return {'phase': 'satisfied', 'gained': 0, 'target_logs': target_logs}
    plan = observed_chop_plan(skills, before, skills.scan(), target_logs)
    if plan is None:
        raise Paused('No observed local native-tree candidate or safe support material')
    if plan['support_needed']:
        skills.gather({'dirt', 'grass_block'}, {'dirt'}, 1)
        before = skills.b.read()
        plan = observed_chop_plan(skills, before, skills.scan(), target_logs)
        if plan is None or plan['support_needed']:
            raise Paused('Tree candidate or dirt support changed before native chopping')
    survey = skills.b.request('scan_trees', item=plan['item'], radius=8)
    if not any(tree['pos'] == plan['observed_root'] for tree in survey['tree_survey']['trees']):
        raise Paused('The observed local root is not a native-confirmed natural tree')
    before = skills.b.read()
    fresh_world = skills.scan()
    fresh_plan = observed_chop_plan(skills, before, fresh_world, target_logs)
    if (fresh_plan is None or fresh_plan['support_needed']
            or fresh_plan['item'] != plan['item'] or fresh_plan['observed_root'] != plan['observed_root']):
        raise Paused('Tree or local inventory changed after native survey; no chop sent')
    before = skills.b.read()
    # Fresh scan/plan above checked the maximum free-selector protection scope,
    # not just the surveyed root. No fixed-tree authority is claimed.
    if not native_chop_protection_clear(skills, before, fresh_world):
        raise Paused('Protected wood or camp can enter the native free-tree selector; no chop sent')
    result = skills.b.request('chop', item=plan['item'], target_count=fresh_plan['target_count'],
                              tree_limit=1, seconds=240, _chop_origin=cell(before['pos']))
    # The bridge requires native cleanup, exact receipt and fresh inventory
    # before acknowledging this mutation. It never blindly retries a batch.
    after = skills.b.read()
    item = plan['item'].removeprefix('minecraft:')
    gained = inventory(after).get(item, 0) - inventory(before).get(item, 0)
    if gained <= 0:
        raise Paused('Native tree ended without log inventory gain; observe its drops before another batch')
    total = sum(inventory(after).get(log.removeprefix('minecraft:'), 0) for log in LOG_IDS)
    proof = {'phase': 'progress', 'request_id': result['id'], 'native_phase': result['phase'],
             'item': plan['item'], 'gained': gained, 'target_logs': target_logs,
             'verified_log_total': total, 'target_reached': total >= target_logs,
             'selection': 'native_nearest_natural_tree_of_surveyed_species'}
    skills.event('native_chop_batch', **proof)
    return proof
