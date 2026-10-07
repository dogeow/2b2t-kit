"""Exact-save, exact-run native interactions for an opted-in disposable trial.

The model never writes this mailbox. Unknown native results stop the run; the
trial's normal death/respawn is a separate, rate-limited native operation.
"""
import json
import math
import time
import uuid
from pathlib import Path

from decisions import DecisionError, status
from survival_bridge import Paused

MENUS = {'', 'InventoryScreen', 'CraftingScreen', 'FurnaceScreen',
         'BlastFurnaceScreen', 'SmokerScreen'}
OPS = frozenset({'snapshot', 'scan', 'walk', 'walk_path', 'mine_block',
                 'select_item', 'slot_click', 'close_menu', 'craft_recipe',
                 'interact', 'attack_passive', 'use_item', 'decision_screenshot',
                 'trial_respawn', 'trial_stop', 'guard', 'scan_trees', 'chop'})
MUTATING_OPS = frozenset({'mine_block', 'craft_recipe', 'interact', 'slot_click',
                        'select_item', 'use_item', 'attack_passive', 'guard', 'chop'})
GUARD_BLOCKED_OPS = frozenset({'walk', 'walk_path', 'mine_block', 'select_item',
                             'slot_click', 'close_menu', 'craft_recipe', 'interact', 'attack_passive', 'chop'})
GUARD_BUSY_DETAIL = 'Construction guard is defending or eating; wait before changing items or starting work'


class TrialDeath(Paused):
    pass


class TrialGuardBusy(Paused):
    """The native guard retained control before any requested action was sent."""
    def __init__(self, op, arguments, receipt=None):
        super().__init__(GUARD_BUSY_DETAIL)
        self.op, self.arguments, self.receipt = op, arguments, receipt


def guard_pre_dispatch_refusal(op, result, expected_revision):
    # AutomationBridge's exact message precedes all action-specific dispatch.
    # Its generic error snapshot intentionally lacks an operation/sequence.
    no_sequence = lambda value: value is None or type(value) is int and value == -1
    not_sent_flag = lambda key: key not in result or result[key] is False
    return (op in GUARD_BLOCKED_OPS and result.get('phase') == 'error'
            and result.get('detail') == GUARD_BUSY_DETAIL
            and result.get('op') in (None, op)
            and result.get('server') == 'singleplayer'
            and result.get('guard_armed') is True and result.get('guard_busy') is True
            and result.get('manual_movement') is False
            and type(result.get('control_revision')) is int
            and result['control_revision'] == expected_revision
            and all(no_sequence(result.get(key)) for key in ('native_sequence', 'server_ack_sequence'))
            and all(not_sent_flag(key) for key in ('outcome_pending', 'server_confirmed', 'server_update_seen'))
            and result.get('confirmation_scope') in (None, 'none'))


class TrialImageUnavailable(Paused):
    """A matched read-only image was refused because a player menu is open."""
    pass


def image_interface_refusal(op, result):
    return (op == 'decision_screenshot' and result.get('phase') == 'error'
            and result.get('detail') == 'Close the game interface before requesting a world image'
            and result.get('screen') in MENUS - {''}
            and not result.get('decision_image') and result.get('outcome_pending') is not True
            and result.get('manual_movement') is False)


class TrialMovementBlocked(Paused):
    """A matched native walking refusal whose owned movement keys are released."""
    def __init__(self, op, arguments, receipt):
        super().__init__('Native walking route refused and stopped; observe a different route')
        self.op = op
        self.arguments = arguments
        self.receipt = receipt


class TrialMiningRejected(Paused):
    """Native sequence proof confirms that this target never dispatched a dig."""
    def __init__(self, arguments, receipt):
        super().__init__(receipt['detail'])
        self.arguments = arguments
        self.receipt = receipt


def confirmed_mining_not_sent(op, result, arguments):
    keys = result.get('movement_keys')
    return (op == 'mine_block' and result.get('op') == op
            and result.get('phase') == 'waiting'
            and result.get('detail') in {'mining target is occluded', 'Mining target out of reach',
                                         'mining target moved out of reach'}
            and result.get('requested_confirmation_scope') == 'single_target_server_block_update_and_native_sequence_ack'
            and result.get('confirmation_scope') == 'none'
            and type(result.get('native_sequence')) is int and result['native_sequence'] == -1
            and type(result.get('server_ack_sequence')) is int and result['server_ack_sequence'] == -1
            and result.get('outcome_pending') is False
            and result.get('server_update_seen') is False
            and result.get('server_confirmed') is False
            and result.get('mining_target') == arguments.get('pos')
            and result.get('server') == 'singleplayer'
            and isinstance(keys, dict) and set(keys) >= {'forward', 'back', 'jump', 'sneak'}
            and all(value is False for value in keys.values()))


def confirmed_movement_refusal(op, result):
    keys = result.get('movement_keys')
    return (op in {'walk', 'walk_path'} and result.get('op') == op
            and result.get('phase') == 'waiting'
            and result.get('detail') == 'unsafe drop ahead; choose another walking waypoint'
            and result.get('server') == 'singleplayer'
            and result.get('outcome_pending') is not True
            and isinstance(keys, dict) and set(keys) >= {'forward', 'back', 'jump', 'sneak'}
            and all(value is False for value in keys.values()))


def walking_signature(op, arguments):
    if op == 'walk_path':
        points = arguments.get('path', [])
    elif op == 'walk':
        points = [arguments.get('target', [])]
    else:
        return None
    return op, tuple(tuple(point) for point in points)


def complete_scan(result, arguments, expected_revision):
    """Only a complete same-revision volume can make omitted cells mean air."""
    low, high = arguments.get('min'), arguments.get('max')
    if (not isinstance(low, (list, tuple)) or not isinstance(high, (list, tuple))
            or len(low) != 3 or len(high) != 3
            or any(type(value) is not int for value in (*low, *high))
            or any(start > end for start, end in zip(low, high))):
        return False
    volume = math.prod(end - start + 1 for start, end in zip(low, high))
    revision = result.get('control_revision')
    return (result.get('phase') == 'done' and isinstance(result.get('blocks'), list)
            and type(revision) is int and revision == expected_revision
            and all(type(result.get(key)) is int and result[key] == volume
                    for key in ('scan_cells_read', 'scan_total_cells'))
            and all(type(result.get(key)) is int and result[key] == revision
                    for key in ('scan_start_revision', 'scan_end_revision')))


def canonical_save(value):
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise Paused('Trial requires an absolute registered save identity')
    return str(Path(value).resolve())


def validate_registry(value, game):
    if (not isinstance(value, dict) or value.get('protocol') != 1
            or value.get('enabled') is not True or value.get('goal') != 'defeat_ender_dragon'
            or value.get('allow_death_respawn') is not True
            or not isinstance(value.get('trial_id'), str)
            or not 1 <= len(value['trial_id']) <= 96
            or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in value['trial_id'])
            or not isinstance(value.get('world_name'), str) or not value['world_name']):
        raise Paused('No explicitly registered disposable survival trial')
    supplied = Path(value.get('world_id', ''))
    save = Path(canonical_save(value.get('world_id')))
    saves = (Path(game) / 'saves').resolve()
    if save.parent != saves or supplied.is_symlink():
        raise Paused('Registered trial must be one direct local save, not a linked or external world')
    return {**value, 'world_id': str(save)}


def validate_scope(state, registry, session=None, run_id=None, allow_dead=False):
    if (not isinstance(state, dict) or state.get('connected') is not True
            or state.get('server') != 'singleplayer' or state.get('game_mode') != 'survival'
            or state.get('singleplayer_trial_protocol') != 1
            or canonical_save(state.get('world_id')) != registry['world_id']
            or state.get('world_name') != registry['world_name']):
        raise Paused('Current world is not the registered singleplayer survival trial')
    identity = state.get('trial_identity', {})
    if (identity.get('registered') is not True
            or identity.get('trial_id') != registry['trial_id']
            or canonical_save(identity.get('world_id')) != registry['world_id']):
        raise Paused('Native trial identity differs from the registered save')
    if session is not None and state.get('world_session') != session:
        raise Paused('Trial connection changed; rebind only through native Start/Resume')
    if run_id is not None and identity.get('run_id') != run_id:
        raise Paused('Native trial run ownership changed')
    dead = state.get('player_dead') is True or state.get('health', 0) <= 0
    if dead and not allow_dead:
        raise TrialDeath('Trial player died; stop the macro before normal respawn')
    if state.get('manual_movement') is True:
        raise Paused('Manual input owns the trial; pause until native Resume')
    screen = state.get('screen', '')
    if screen not in MENUS and not (allow_dead and dead and screen == 'DeathScreen'):
        raise Paused('A player interface owns control; pause until native Resume')
    if state.get('game_paused') is True and not (dead and allow_dead):
        raise Paused('Integrated server is paused')
    pos = state.get('pos')
    if (not isinstance(pos, list) or len(pos) != 3
            or any(type(n) not in (int, float) or not math.isfinite(n) for n in pos)):
        raise Paused('Invalid native trial position')
    if type(state.get('control_revision')) is not int:
        raise Paused('Missing native control revision')
    return state


class TrialBridge:
    def __init__(self, root, registry, run_id, check_control=lambda: None,
                 heartbeat=lambda state: None, events=lambda *a, **k: None,
                 reader=status, sleeper=time.sleep):
        self.root = Path(root)
        self.registry = registry
        self.world = registry['world_name']
        self.run_id = run_id
        self.check_control = check_control
        self.heartbeat = heartbeat
        self.events = events
        self.reader = reader
        self.sleeper = sleeper
        first = validate_scope(self.reader(self.root), registry, run_id=run_id, allow_dead=True)
        self.session = first['world_session']
        self.revision = first['control_revision']
        self.last = first.get('last_request', '')
        self.origin = list(first['pos'])
        self.state = first
        self.active = None
        self.owned = False
        self.halted = False
        self.last_receipt = None
        self.receipts = []
        self.minimum_time = 0
        self.rejected_paths = {}
        self.pending_mutations = {}

    def observe(self, deadline=None):
        deadline = time.monotonic() + 6 if deadline is None else deadline
        while True:
            try:
                state = self.reader(self.root)
            except DecisionError as error:
                # A slow native scan/status writer may temporarily exceed the
                # ordinary status age. Wait for this same request, never send a
                # second request or reinterpret other observation failures.
                if str(error) != 'Game observation is stale':
                    raise
                state = None
            if state is not None and state.get('time', 0) >= self.minimum_time:
                return state
            self.check_control()
            if time.monotonic() >= deadline:
                raise Paused('Fresh native observation was not confirmed before its deadline; do not replay')
            self.sleeper(.05)

    def read(self, allow_dead=False, deadline=None):
        self.check_control()
        if self.halted:
            raise Paused('Unknown or handed-over native operation; no automatic replay')
        state = validate_scope(self.observe(deadline=deadline), self.registry, self.session,
                               self.run_id, allow_dead=allow_dead)
        if (state['control_revision'] != self.revision
                or state.get('last_request', '') != self.last):
            self.halted = True
            raise Paused('Native revision or another controller changed')
        self.state = state
        self.heartbeat(state)
        return state

    def request(self, op, **args):
        if op not in OPS:
            raise Paused('Trial primitive is not explicitly supported: ' + str(op))
        chop_origin = args.pop('_chop_origin', None)
        if chop_origin is not None and (op != 'chop' or not isinstance(chop_origin, (list, tuple))
                or len(chop_origin) != 3 or any(type(n) is not int for n in chop_origin)):
            raise Paused('Invalid local native-chop observation origin; no action sent')
        deadline = time.monotonic() + max(12, min(600, args.get('seconds', 20)) + 15)
        state = self.read(allow_dead=op in {'trial_respawn', 'trial_stop'}, deadline=deadline)
        if op == 'chop':
            from trial_native_chop import validate_chop_arguments
            validate_chop_arguments(state, args)
            if chop_origin is None:
                chop_origin = tuple(math.floor(n) for n in state['pos'])
        guard_waited = False
        while (op in GUARD_BLOCKED_OPS and state.get('guard_armed') is True
               and state.get('guard_busy') is True):
            # No mailbox/action is created while native defense or eating owns
            # the player. Every refreshed frame retains exact run/manual/revision
            # checks and uses this same bounded request budget.
            if time.monotonic() >= deadline:
                raise TrialGuardBusy(op, args)
            guard_waited = True
            self.sleeper(.1)
            state = self.read(allow_dead=op in {'trial_respawn', 'trial_stop'}, deadline=deadline)
        if time.monotonic() >= deadline:
            if guard_waited:
                raise TrialGuardBusy(op, args)
            raise Paused('Trial request observation budget expired before dispatch; no action sent')
        if op == 'chop':
            # Native defense may have changed inventory while this request
            # waited; scope and bounded batch prerequisites are checked again.
            validate_chop_arguments(state, args)
            if tuple(math.floor(n) for n in state['pos']) != tuple(chop_origin):
                raise Paused('Native chop observation origin changed before dispatch; reobserve without replay')
        signature = walking_signature(op, args)
        if signature in self.rejected_paths:
            raise TrialMovementBlocked(op, args, self.rejected_paths[signature])
        if op == 'trial_respawn' and not (state.get('player_dead') or state.get('health', 20) <= 0):
            raise Paused('No native death to respawn')
        pending = self.root / 'request.json'
        if pending.exists():
            previous = json.loads(pending.read_text())
            if previous.get('id') not in {self.last, self.active}:
                raise Paused('Foreign or unresolved native mailbox; preserve it')
        request_id = 'trial-' + uuid.uuid4().hex[:20]
        envelope = {'id': request_id, 'op': op, 'server': 'singleplayer',
                    'dimension': state['dimension'], 'site': list(state['pos']),
                    'world_session': self.session, 'world_id': self.registry['world_id'],
                    'trial_id': self.registry['trial_id'], 'run_id': self.run_id,
                    'local_trial': True, 'local_survival': True, 'background_ok': True,
                    'expected_revision': self.revision,
                    'expires_at': int(time.time() * 1000) + 10000, **args}
        # Callers are local skills, but they cannot replace the verified envelope.
        for field in ('id', 'op', 'server', 'dimension', 'world_session', 'world_id',
                      'trial_id', 'run_id', 'local_trial', 'local_survival',
                      'expected_revision', 'expires_at'):
            if field in args:
                raise Paused('Primitive arguments cannot replace trial scope')
        temp = self.root / (request_id + '.tmp')
        temp.write_text(json.dumps(envelope, allow_nan=False))
        self.events('native_request', id=request_id, op=op, arguments=args)
        temp.replace(pending)
        self.active = request_id
        self.owned = True
        if op in MUTATING_OPS:
            self.pending_mutations[request_id] = {'id': request_id, 'op': op,
                'world_session': self.session, 'arguments': args}
            if op == 'chop':
                self.pending_mutations[request_id].update({key: envelope[key]
                    for key in ('world_id', 'trial_id', 'run_id', 'dimension')})
        while time.monotonic() < deadline:
            self.check_control()
            current = self.observe(deadline=deadline)
            validate_scope(current, self.registry, None if op == 'trial_respawn' else self.session, self.run_id,
                           allow_dead=op in {'trial_respawn', 'trial_stop'})
            self.heartbeat(current)
            path = self.root / ('reply-' + request_id + '.json')
            result = json.loads(path.read_text()) if path.exists() else current
            matched = result.get('id') == request_id and (path.exists() or current.get('last_request') == request_id)
            # Scan status can inherit a preceding action's phase; the exact
            # payload itself still needs the full native scan contract below.
            if op == 'scan':
                completed = 'blocks' in result
            elif op == 'scan_trees':
                completed = 'tree_survey' in result or result.get('phase') == 'error'
            else:
                completed = result.get('phase') in {'done', 'waiting', 'error', 'stopped'}
            terminal = matched and completed
            if terminal:
                validate_scope(result, self.registry, None if op == 'trial_respawn' else self.session, self.run_id,
                               allow_dead=op in {'trial_respawn', 'trial_stop'})
                if current.get('last_request') not in {self.last, request_id}:
                    self.halted = True
                    raise Paused('Another native controller took over before the result')
                if op == 'chop' and (result.get('phase') == 'done' and
                        (result['control_revision'] != envelope['expected_revision'] + 1
                         or current['control_revision'] != result['control_revision'])):
                    self.halted = True
                    raise Paused('Native chopper revision changed outside its single admitted handoff')
                self.last = request_id
                if op == 'trial_respawn' and result.get('phase') == 'done':
                    self.session = result['world_session']
                self.revision = result['control_revision']
                self.minimum_time = result.get('time', 0)
                self.state = result
                self.active = None
                self.last_receipt = {**result, 'native': True, 'request_id': request_id}
                self.receipts.append(self.last_receipt)
                self.receipts = self.receipts[-128:]
                self.events('native_result', id=request_id, op=op,
                            phase=result.get('phase'), position=result.get('pos'))
                if op == 'scan' and not complete_scan(result, args, envelope['expected_revision']):
                    self.halted = True
                    raise Paused('Native scan volume or revision is incomplete; no terrain actions permitted')
                if op == 'scan_trees':
                    from trial_native_chop import complete_tree_survey
                    if (not complete_tree_survey(result, args, envelope['expected_revision'], envelope['site'])
                            or current['control_revision'] != envelope['expected_revision']):
                        self.halted = True
                        raise Paused('Native tree survey payload or revision is incomplete; no chopping permitted')
                    self.last_receipt = {**self.last_receipt, 'receipt_class': 'native_tree_survey'}
                    self.receipts[-1] = self.last_receipt
                if op not in {'scan', 'scan_trees'} and result.get('phase') != 'done':
                    if (current['control_revision'] == envelope['expected_revision']
                            and guard_pre_dispatch_refusal(op, result, envelope['expected_revision'])):
                        self.pending_mutations.pop(request_id, None)
                        self.last_receipt = {**self.last_receipt, 'code': 'guard_pre_dispatch_refusal',
                                             'receipt_class': 'native_guard_busy_before_dispatch'}
                        self.receipts[-1] = self.last_receipt
                        raise TrialGuardBusy(op, args, self.last_receipt)
                    if image_interface_refusal(op, result):
                        self.last_receipt = {**self.last_receipt, 'code': 'image_interface_refusal',
                                             'receipt_class': 'read_only_image_refusal'}
                        self.receipts[-1] = self.last_receipt
                        raise TrialImageUnavailable('Player interface is open; wait for it to close before observing another world image')
                    if confirmed_mining_not_sent(op, result, args):
                        self.pending_mutations.pop(request_id, None)
                        self.last_receipt = {**self.last_receipt, 'code': 'pre_dispatch_refusal',
                                             'receipt_class': 'mining_pre_dispatch_refusal'}
                        self.receipts[-1] = self.last_receipt
                        raise TrialMiningRejected(args, self.last_receipt)
                    if confirmed_movement_refusal(op, result):
                        self.last_receipt = {**self.last_receipt, 'code': 'path_blocked',
                                             'receipt_class': 'terrain_movement_refusal'}
                        self.receipts[-1] = self.last_receipt
                        self.rejected_paths[signature] = self.last_receipt
                        raise TrialMovementBlocked(op, args, self.last_receipt)
                    self.halted = True
                    raise Paused('Native operation did not complete: ' + result.get('detail', 'unknown outcome'))
                if op == 'chop':
                    from trial_native_chop import record_chop_receipt
                    try:
                        record_chop_receipt(self.root, envelope, state, result)
                    except (OSError, ValueError, Paused):
                        self.halted = True
                        raise
                if result.get('phase') == 'done' and result.get('outcome_pending') is not True:
                    self.pending_mutations.pop(request_id, None)
                return result
            if current.get('last_request') == request_id:
                if op == 'chop' and current['control_revision'] not in {envelope['expected_revision'], envelope['expected_revision'] + 1}:
                    self.halted = True
                    raise Paused('Another revision interrupted the native chopper; preserve its intent')
                self.revision = current['control_revision']
            elif current.get('last_request') != self.last or current['control_revision'] != self.revision:
                self.halted = True
                raise Paused('Foreign native request interrupted the trial')
            self.sleeper(.1)
        self.halted = True
        raise Paused('Native operation has an unknown outcome; preserve request and do not retry')

    def click(self, slot, kind='pickup', button=0):
        state = self.read()
        row = state['menu']['slots'][slot]
        return self.request('slot_click', menu_id=state['menu']['id'], slot=slot,
                            kind=kind, button=button, expected_item=row['item'],
                            expected_count=row['count'])

    def select(self, item):
        return self.request('select_item', item='minecraft:' + item)

    def close(self):
        if self.read()['menu']['id'] != 0:
            return self.request('close_menu')

    def wait(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.read()
            self.sleeper(min(.2, max(0, deadline - time.monotonic())))

    def stop_owned(self):
        # Native UI Pause/Cancel stops the exact run immediately. This cleanup
        # may only ask for the same run; it must never issue global "stop".
        try:
            state = self.reader(self.root)
            validate_scope(state, self.registry, self.session, self.run_id, allow_dead=True)
            if not self.owned or state.get('last_request') not in {self.last, self.active}:
                return
            pending = self.root / 'request.json'
            if pending.exists() and json.loads(pending.read_text()).get('id') not in {self.last, self.active}:
                return
            request_id = 'trial-stop-' + uuid.uuid4().hex[:12]
            request = {'id': request_id, 'op': 'trial_stop', 'server': 'singleplayer',
                       'dimension': state['dimension'], 'site': state['pos'],
                       'world_session': self.session, 'world_id': self.registry['world_id'],
                       'trial_id': self.registry['trial_id'], 'run_id': self.run_id,
                       'local_trial': True, 'background_ok': True,
                       'expected_revision': state['control_revision'],
                       'expires_at': int(time.time() * 1000) + 5000}
            temp = self.root / (request_id + '.tmp')
            temp.write_text(json.dumps(request))
            temp.replace(pending)
        except (OSError, ValueError, DecisionError):
            pass
