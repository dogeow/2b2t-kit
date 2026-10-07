"""Exact-save, exact-run native interactions for an opted-in disposable trial.

The model never writes this mailbox. Unknown native results stop the run; the
trial's normal death/respawn is a separate, rate-limited native operation.
"""
import json
import copy
import hashlib
import math
import os
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
                 'trial_respawn', 'trial_stop', 'guard', 'scan_trees', 'chop', 'inventory_probe'})
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


class TrialInteractionRejected(Paused):
    """The exact native face check refused before rotation or useItemOn."""
    def __init__(self, arguments, receipt):
        super().__init__(receipt['detail'])
        self.arguments = arguments
        self.receipt = receipt


def confirmed_interaction_not_sent(op, result, arguments, expected_revision):
    """Recognize only the reviewed .7/.8/.9 ordinary-interaction preflight path.

    AutomationBridge checks BlockFaceTarget.visible before assigning active or
    queuing PlacementRotation. The receive catch writes the exception message
    without an operation field. Later rotation/use exceptions have different
    messages; missing acknowledgements alone are never a no-send proof.
    Exact request identity/world/run binding remains the caller's obligation.
    """
    if (not isinstance(result, dict) or type(expected_revision) is not int
            or not isinstance(arguments, dict)
            or set(arguments) - {'pos', 'face', 'expected_state', 'expected_hand', 'seconds'}):
        return False
    point = arguments.get('pos')
    keys = result.get('movement_keys')
    menu = result.get('menu', {})
    if (not isinstance(menu, dict) or not isinstance(menu.get('cursor'), dict)
            or not isinstance(menu.get('slots', []), list)
            or any(not isinstance(row, dict) for row in menu.get('slots', []))
            or not isinstance(result.get('hand'), dict)):
        return False
    no_sequence = lambda value: value is None or type(value) is int and value == -1
    return (op == 'interact' and result.get('phase') == 'error'
            and result.get('detail') == 'Target interaction face is occluded or out of reach'
            and result.get('op') in (None, 'interact')
            and isinstance(point, (list, tuple)) and len(point) == 3
            and all(type(n) is int for n in point)
            and arguments.get('face') in ('up', 'down', 'north', 'south', 'east', 'west')
            and isinstance(arguments.get('expected_state'), str) and arguments['expected_state'].startswith('Block{minecraft:')
            and isinstance(arguments.get('expected_hand'), str) and arguments['expected_hand'].startswith('minecraft:')
            and result.get('kit_version') in {'2026.10.7.7', '2026.10.7.8', '2026.10.7.9'}
            and result.get('bridge_version') == 4 and result.get('game_version') == '26.1.2'
            and result.get('server') == 'singleplayer' and result.get('manual_movement') is False
            and result.get('screen') == '' and result.get('game_paused') is False
            and type(result.get('control_revision')) is int and result['control_revision'] == expected_revision
            and result.get('hand', {}).get('item') == arguments['expected_hand']
            and type(menu.get('id')) is int and menu['id'] == 0 and menu.get('type') == 'InventoryMenu'
            and type(menu.get('cursor', {}).get('count')) is int and menu['cursor']['count'] == 0
            and not any(row.get('count', 0) for row in menu.get('slots', [])[1:5])
            and isinstance(keys, dict) and set(keys) >= {'forward', 'back', 'jump', 'sneak'}
            and all(value is False for value in keys.values())
            and all(no_sequence(result.get(key)) for key in ('native_sequence', 'server_ack_sequence'))
            and all(key not in result or result[key] is False
                    for key in ('outcome_pending', 'server_confirmed', 'server_update_seen'))
            and result.get('confirmation_scope') in (None, 'none')
            and result.get('requested_confirmation_scope') in (None, 'none'))


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


class TrialInventoryNoEffect(Paused):
    """The exact click was processed, with no inventory transition; never NoSend."""
    def __init__(self, arguments, receipt):
        super().__init__('Server processed the inventory click without an item transition; reobserve before a new intent')
        self.arguments, self.receipt = arguments, receipt


def inventory_menu_signature(menu):
    if (not isinstance(menu, dict) or type(menu.get('id')) is not int
            or menu.get('type') not in {'InventoryMenu', 'CraftingMenu'}
            or not isinstance(menu.get('cursor'), dict)
            or not isinstance(menu.get('slots'), list)
            or len(menu['slots']) < (45 if menu['type'] == 'InventoryMenu' else 46)):
        raise Paused('Incomplete inventory confirmation menu; preserve the click')
    def stack(row):
        if (not isinstance(row, dict) or not isinstance(row.get('item'), str)
                or not row['item'].startswith('minecraft:') or type(row.get('count')) is not int
                or row['count'] < 0):
            raise Paused('Invalid inventory confirmation stack; preserve the click')
        return row['item'], row['count']
    slots = []
    for index, row in enumerate(menu['slots']):
        if not isinstance(row, dict) or type(row.get('slot')) is not int or row['slot'] != index:
            raise Paused('Incomplete inventory confirmation slots; preserve the click')
        slots.append(stack(row))
    return menu['id'], menu['type'], stack(menu['cursor']), tuple(slots)


def native_inventory_click_proof(result, envelope, before):
    """Validate an audited .8/.9 server-processed receipt, never timer done."""
    if not isinstance(result, dict):
        raise Paused('Server inventory click confirmation is malformed; preserve the click')
    proof = result.get('inventory_click_receipt', {})
    if (result.get('kit_version') not in {'2026.10.7.8', '2026.10.7.9'}
            or type(result.get('inventory_click_protocol')) is not int or result['inventory_click_protocol'] != 1
            or result.get('id') != envelope['id'] or result.get('phase') != 'done'
            or result.get('outcome_pending') is True or not isinstance(proof, dict)
            or proof.get('request_id') != envelope['id']
            or proof.get('world_session') != envelope['world_session']
            or type(proof.get('protocol')) is not int or proof['protocol'] != 1 or proof.get('scope_current') is not True
            or proof.get('confirmation_scope') != 'integrated_server_processed_click_and_matching_final_inventory'
            or type(proof.get('native_sequence')) is not int or proof['native_sequence'] <= 0
            or proof.get('correlation_ambiguous') is not False
            or type(proof.get('server_processed_at')) is not int
            or proof.get('slot') != envelope['slot'] or type(proof.get('slot')) is not int
            or proof.get('button') != envelope.get('button', 0) or type(proof.get('button')) is not int
            or proof.get('kind') != envelope['kind']
            or type(proof.get('control_revision')) is not int or proof['control_revision'] != envelope['expected_revision']
            or proof.get('server_processed') is not True
            or proof.get('classification') not in {'confirmed', 'no_effect'}):
        raise Paused('Server inventory click confirmation is missing or unknown; preserve the click')
    if (result.get('world_id') != envelope['world_id'] or result.get('world_session') != envelope['world_session']
            or result.get('dimension') != envelope['dimension'] or result.get('server') != 'singleplayer'
            or result.get('control_revision') != envelope['expected_revision']
            or result.get('trial_identity', {}).get('trial_id') != envelope['trial_id']
            or result.get('trial_identity', {}).get('run_id') != envelope['run_id']):
        raise Paused('Server inventory confirmation belongs to another native scope; preserve the click')
    signatures, complete_stacks, predicted_stacks = {}, {}, {}
    for name in ('before', 'predicted_after', 'server', 'client'):
        view = proof.get(name)
        if (not isinstance(view, dict) or type(view.get('state_id')) is not int
                or type(view.get('quickcraft_status')) is not int
                or type(view.get('observed_at')) is not int or type(view.get('game_time')) is not int
                or view.get('world_id') != envelope['world_id']
                or view.get('dimension') != envelope['dimension']
                or view.get('player_uuid') != before.get('player_uuid')
                or not isinstance(view.get('player_uuid'), str) or not view['player_uuid']
                or not isinstance(view.get('inventory'), list)
                or len(view['inventory']) < 36
                or any(not isinstance(row, dict) or 'stack_data' not in row
                       for row in [view.get('cursor'), *view.get('slots', []), *view['inventory']])):
            raise Paused('Server inventory click scope or full stacks are incomplete; preserve the click')
        signatures[name] = inventory_menu_signature(view)
        complete_stacks[name] = json.dumps({'cursor': view['cursor'], 'slots': view['slots'],
                                           'inventory': view['inventory']}, sort_keys=True, allow_nan=False)
        # The recipe output can first be calculated by the server. Its final
        # client/server values must match, but local prediction of slot 0 is
        # not a receipt for consuming a source, depositing or moving output.
        predicted_stacks[name] = json.dumps({'cursor': view['cursor'], 'slots': view['slots'][1:],
                                            'inventory': view['inventory']}, sort_keys=True, allow_nan=False)
    if (signatures['before'] != inventory_menu_signature(before['menu'])
            or signatures['server'] != signatures['client']
            or complete_stacks['server'] != complete_stacks['client']
            or proof['classification'] == 'confirmed' and predicted_stacks['server'] != predicted_stacks['predicted_after']
            or proof['before']['observed_at'] > proof['server']['observed_at']
            or proof['before']['observed_at'] > proof['client']['observed_at']
            or proof['before']['observed_at'] > proof['server_processed_at']
            or proof['server_processed_at'] > proof['server']['observed_at']
            or proof['server_processed_at'] > proof['client']['observed_at']
            or proof['classification'] == 'no_effect' and complete_stacks['server'] != complete_stacks['before']
            or proof['classification'] == 'no_effect' and (proof['server']['quickcraft_status'] != 0
                                                         or proof['client']['quickcraft_status'] != 0)
            or proof['classification'] == 'no_effect' and signatures['server'] != signatures['before']
            or proof['classification'] == 'confirmed' and signatures['server'] == signatures['before']):
        raise Paused('Server inventory click transition differs from the exact SDK intent; preserve the click')
    return proof


def native_inventory_probe_proof(result, envelope, before):
    """Current server/client views never supply historical click evidence."""
    probe = result.get('inventory_probe', {})
    if (result.get('kit_version') not in {'2026.10.7.8', '2026.10.7.9'} or result.get('id') != envelope['id']
            or result.get('phase') != 'done' or not isinstance(probe, dict)
            or type(probe.get('protocol')) is not int or probe['protocol'] != 1
            or probe.get('request_id') != envelope['id']
            or probe.get('world_session') != envelope['world_session']
            or type(probe.get('control_revision')) is not int or probe['control_revision'] != envelope['expected_revision']
            or probe.get('scope_current') is not True or probe.get('server_observed') is not True
            or probe.get('audit_scope') != 'current_state_only_not_historical_dispatch'):
        raise Paused('Exact current inventory probe scope was not confirmed; no inventory action permitted')
    for name in ('server', 'client'):
        value = probe.get(name)
        if (not isinstance(value, dict) or value.get('world_id') != envelope['world_id']
                or value.get('dimension') != envelope['dimension']
                or value.get('player_uuid') != before.get('player_uuid')
                or not isinstance(value.get('player_uuid'), str) or not value['player_uuid']
                or type(value.get('state_id')) is not int or type(value.get('quickcraft_status')) is not int
                or type(value.get('game_time')) is not int or type(value.get('observed_at')) is not int
                or value['observed_at'] < before['time']
                or not 0 <= time.time() - value['observed_at'] / 1000 <= 3
                or not isinstance(value.get('inventory'), list) or len(value['inventory']) < 36
                or any(not isinstance(row, dict) or 'stack_data' not in row
                       for row in [value.get('cursor'), *value.get('slots', []), *value['inventory']])):
            raise Paused('Current inventory probe contains incomplete or stale server/client views')
        inventory_menu_signature(value)
    return probe


def trial_auto_refill_ready(state):
    """Only the .9 observed hook can own cursor isolation against present IPN."""
    guard = state.get('auto_refill_guard')
    if (state.get('kit_version') != '2026.10.7.9' or not isinstance(guard, dict)
            or type(guard.get('protocol')) is not int or guard['protocol'] != 1
            or type(guard.get('ipn_present')) is not bool or guard.get('supported') is not True
            or guard.get('active') is not True
            or type(state.get('time')) is not int or not 0 <= time.time() * 1000 - state['time'] <= 1000):
        return False
    isolation = state.get('inventory_isolation', {})
    if isolation.get('ipn_present', guard['ipn_present']) is not guard['ipn_present']:
        return False
    if not guard['ipn_present']:
        return True
    return (guard.get('hook_seen') is True and guard.get('suppressed') is True
            and type(guard.get('suppressed_ticks')) is int and guard['suppressed_ticks'] > 0
            and all(type(guard.get(key)) is int and 0 <= state['time'] - guard[key] <= 1000
                    and 0 <= time.time() * 1000 - guard[key] <= 1000
                    for key in ('last_hook_at', 'last_suppressed_at')))


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
                 reader=status, sleeper=time.sleep, retired_inventory=None, parent_pid=None):
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
        self.sdk_inventory_pending = {}
        self.historical_inventory_pending = {}
        self.retired_inventory = copy.deepcopy(retired_inventory)
        self.parent_pid = parent_pid
        self.inventory_replan = None
        self.historical_inventory_frozen = {}
        self.last_inventory_probe = None
        self._restore_inventory_intents()

    def _inventory_paths(self, request_id):
        root = self.root / 'trial-sdk-inventory'
        return root / 'pending' / (request_id + '.json'), root / 'receipts' / (request_id + '.json')

    def _durable_json(self, path, value):
        if not path.is_relative_to(self.root):
            raise Paused('Inventory evidence path is outside the bound controller')
        parents = []
        for parent in path.parents:
            parents.append(parent)
            if parent == self.root:
                break
        if path.is_symlink() or any(parent.is_symlink() for parent in parents):
            raise Paused('Inventory evidence path is linked; preserve the click')
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.tmp')
        if temp.is_symlink():
            raise Paused('Inventory evidence temporary path is linked; preserve the click')
        with temp.open('w') as stream:
            json.dump(value, stream, allow_nan=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(path)

    def _restore_inventory_intents(self):
        folder = self.root / 'trial-sdk-inventory' / 'pending'
        if folder.is_symlink():
            raise Paused('Inventory pending evidence is linked; no replay')
        if not folder.exists():
            if self.retired_inventory:
                raise Paused('Retired SDK admission lacks its original pending directory')
            return
        admitted = {}
        if self.retired_inventory:
            if (not isinstance(self.retired_inventory, list) or not 1 <= len(self.retired_inventory) <= 4
                    or type(self.parent_pid) is not int or self.parent_pid <= 1):
                raise Paused('Retired SDK inventory lacks a bounded new-parent admission')
            from trial_inventory_audit import validate_retired_inventory
            for metadata in self.retired_inventory:
                claim = validate_retired_inventory(metadata, self.registry, self.state, self.parent_pid)
                original = claim.get('request', {})
                rid = original.get('id')
                if (rid in admitted or not isinstance(claim.get('sdk_pending'), dict)
                        or not isinstance(claim.get('frozen'), dict)
                        or claim.get('historical_effects_unresolved') is not True
                        or claim.get('old_action_completed') is not False or claim.get('old_action_replayed') is not False
                        or original.get('run_id') == self.run_id or original.get('world_session') == self.session
                        or original.get('world_id') != self.registry['world_id']
                        or original.get('trial_id') != self.registry['trial_id']):
                    raise Paused('Retired SDK inventory admission differs from the exact new scope')
                admitted[rid] = claim
        for path in folder.glob('trial-*.json'):
            if path.is_symlink() or path.stat().st_size > 512_000:
                raise Paused('Invalid inventory pending evidence; no replay')
            record = json.loads(path.read_text())
            envelope = record.get('envelope', {})
            if envelope.get('world_id') != self.registry['world_id']:
                continue
            request_id = envelope.get('id')
            if (record.get('protocol') != 1 or envelope.get('op') != 'slot_click'
                    or envelope.get('inventory_confirm') is not True or path.stem != request_id):
                raise Paused('Malformed same-world SDK inventory intent; no replay')
            unused, receipt_path = self._inventory_paths(request_id)
            settled = False
            if receipt_path.exists():
                if receipt_path.is_symlink() or receipt_path.stat().st_size > 1_000_000:
                    raise Paused('Invalid inventory confirmation evidence; no replay')
                receipt = json.loads(receipt_path.read_text())
                match = (receipt.get('protocol') == 1 and receipt.get('request_id') == request_id
                         and receipt.get('intent_sha256') == hashlib.sha256(path.read_bytes()).hexdigest())
                if receipt.get('receipt_class') == 'native_guard_busy_before_inventory_dispatch':
                    value = receipt.get('native_result', {})
                    validate_scope(value, self.registry, envelope['world_session'], envelope['run_id'])
                    settled = (match and value.get('id') == request_id
                               and guard_pre_dispatch_refusal('slot_click', value, envelope['expected_revision']))
                else:
                    proof = native_inventory_click_proof(receipt.get('native_result', {}), envelope, record['before'])
                    stamps = receipt.get('witness_times', [])
                    settled = (match and (proof['classification'] == 'no_effect'
                                and receipt.get('receipt_class') == 'server_processed_inventory_click_no_effect'
                                or proof['classification'] == 'confirmed'
                                and receipt.get('receipt_class') == 'sdk_inventory_click_committed'
                                and receipt.get('sdk_predicate_confirmed') is True
                                and isinstance(stamps, list) and len(stamps) == 2
                                and all(type(stamp) is int for stamp in stamps)
                                and receipt['native_result']['time'] < stamps[0] < stamps[1]))
                if not settled:
                    raise Paused('Inventory confirmation evidence is incomplete; no replay')
            if not settled:
                if request_id in admitted:
                    claim = admitted.pop(request_id)
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if (record != claim['sdk_pending'] or envelope != claim['request']
                            or claim['frozen'].get(str(path.resolve())) != digest):
                        raise Paused('Original durable SDK pending differs from its retired frozen evidence')
                    self.historical_inventory_pending[request_id] = copy.deepcopy(record)
                    self.historical_inventory_frozen.update(claim['frozen'])
                    self.historical_inventory_frozen[str(path.resolve())] = digest
                    continue
                self.pending_mutations[request_id] = {'id': request_id, 'op': 'slot_click',
                    'world_session': envelope['world_session'], 'arguments': record['arguments'],
                    'sdk_inventory_pending': True, 'intent_path': str(path)}
                self.sdk_inventory_pending[request_id] = record
                self.halted = True
        if admitted:
            raise Paused('A retired admission lacks its original unresolved durable SDK pending')
        self._verify_historical_inventory()

    def _verify_historical_inventory(self):
        for filename, digest in self.historical_inventory_frozen.items():
            path = Path(filename)
            if (not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents))
                    or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
                self.halted = True
                raise Paused('Retired SDK inventory evidence changed; preserve all unknown intents')

    def _inventory_replan_current(self):
        baseline = self.inventory_replan
        return (isinstance(baseline, dict)
                and all(baseline.get(key) == value for key, value in {
                    'world_id': self.registry['world_id'], 'trial_id': self.registry['trial_id'],
                    'run_id': self.run_id, 'world_session': self.session,
                    'dimension': self.state.get('dimension')}.items()))

    def authorize_inventory_replan(self, baseline):
        """Admit new current facts after review; retain every historical unknown."""
        if not self.historical_inventory_pending:
            return
        self._verify_historical_inventory()
        current = self.read()
        identifiers = set(self.historical_inventory_pending)
        if (self.halted or self.pending_mutations or self.active is not None
                or not isinstance(baseline, dict) or baseline.get('schema') != 1
                or baseline.get('source') != 'fresh_kit_physical_baseline'
                or not isinstance(baseline.get('newbaseline_id'), str) or not baseline['newbaseline_id']
                or baseline.get('historical_effects_unresolved') is not True
                or baseline.get('old_action_completed') is not False or baseline.get('old_action_replayed') is not False
                or any(baseline.get(key) != value for key, value in {
                    'world_id': self.registry['world_id'], 'trial_id': self.registry['trial_id'],
                    'run_id': self.run_id, 'world_session': self.session, 'dimension': current['dimension'],
                    'control_revision': self.revision}.items())
                or type(baseline.get('observed_at')) is not int
                or not 0 <= time.time() * 1000 - baseline['observed_at'] <= 3000
                or not isinstance(baseline.get('legacy_pending'), list)
                or not identifiers <= {row.get('id') for row in baseline['legacy_pending'] if isinstance(row, dict)}
                or not isinstance(baseline.get('forbidden_request_ids'), list)
                or not identifiers <= set(baseline['forbidden_request_ids'])
                or not isinstance(baseline.get('inventory_review_verified_ids'), list)
                or set(baseline['inventory_review_verified_ids']) != {
                    row.get('id') for row in baseline['legacy_pending']
                    if isinstance(row, dict) and row.get('op') == 'slot_click'}
                or not identifiers <= set(baseline['inventory_review_verified_ids'])
                or baseline.get('menu') != current.get('menu')
                or baseline.get('inventory') != current.get('inventory')):
            raise Paused('Retired SDK inventory requires this new scope\'s independently reviewed physical baseline')
        probe = self.last_inventory_probe
        if not isinstance(probe, dict):
            raise Paused('A new bridge-owned current inventory probe is required before fresh inventory planning')
        result, envelope = probe['result'], probe['envelope']
        value = native_inventory_probe_proof(result, envelope, probe['before'])
        if (result.get('world_session') != self.session or result.get('control_revision') != self.revision
                or result.get('trial_identity', {}).get('run_id') != self.run_id
                or not 0 <= current['time'] - result['time'] <= 3000
                or inventory_menu_signature(value['client']) != inventory_menu_signature(current['menu'])
                or inventory_menu_signature(value['server']) != inventory_menu_signature(current['menu'])):
            raise Paused('Current SDK physical baseline differs from its fresh server/client probe')
        full = lambda side: json.dumps({key: side[key] for key in ('cursor', 'slots', 'inventory')}, sort_keys=True)
        if full(value['client']) != full(value['server']):
            raise Paused('Current complete server/client inventory components differ; no fresh inventory plan')
        self.inventory_replan = copy.deepcopy(baseline)
        self.events('historical_sdk_inventory_fresh_plan_admitted', baseline_id=baseline['newbaseline_id'],
                    forbidden_request_ids=sorted(identifiers), historical_effects_unresolved=True,
                    old_action_completed=False, old_action_replayed=False)

    def commit_inventory_click(self, stage, witnesses, predicate):
        if not self.sdk_inventory_pending:
            return None
        if (self.halted or len(self.sdk_inventory_pending) != 1 or not isinstance(stage, str) or not stage
                or not callable(predicate) or not isinstance(witnesses, list) or len(witnesses) != 2):
            raise Paused('SDK inventory commit lacks an exact pending transaction; preserve it')
        request_id, record = next(iter(self.sdk_inventory_pending.items()))
        envelope = record['envelope']
        proof = native_inventory_click_proof(record.get('native_result', {}), envelope, record['before'])
        if proof['classification'] != 'confirmed':
            raise Paused('An unchanged or unknown click is not SDK ingredient acknowledgement')
        times = []
        expected = inventory_menu_signature(proof['client'])
        for witness in witnesses:
            validate_scope(witness, self.registry, self.session, self.run_id)
            if (witness.get('last_request') != request_id or witness.get('control_revision') != envelope['expected_revision']
                    or witness.get('dimension') != envelope['dimension']
                    or type(witness.get('time')) is not int
                    or witness['time'] <= record['native_result']['time']
                    or not 0 <= time.time() - witness['time'] / 1000 <= 3
                    or inventory_menu_signature(witness['menu']) != expected or not predicate(witness['menu'])):
                raise Paused('SDK inventory predicate or exact fresh witnesses are not confirmed; preserve the click')
            times.append(witness['time'])
        if times[0] >= times[1]:
            raise Paused('SDK inventory requires two time-advanced confirmations; preserve the click')
        current = self.read()
        if (type(current.get('time')) is not int or current['time'] < times[-1]
                or inventory_menu_signature(current['menu']) != expected or not predicate(current['menu'])):
            raise Paused('SDK inventory changed before commit; preserve the click')
        pending, destination = self._inventory_paths(request_id)
        receipt = {'protocol': 1, 'request_id': request_id, 'receipt_class': 'sdk_inventory_click_committed',
                   'intent_sha256': hashlib.sha256(pending.read_bytes()).hexdigest(),
                   'native_result': record['native_result'], 'sdk_stage': stage,
                   'sdk_predicate_confirmed': True, 'witness_times': times,
                   'confirmation_scope': 'server_processed_inventory_transition_and_two_fresh_sdk_predicates',
                   'replayed': False}
        self._durable_json(destination, receipt)
        self.sdk_inventory_pending.pop(request_id)
        self.pending_mutations.pop(request_id, None)
        self.events('sdk_inventory_click_committed', id=request_id, stage=stage, witness_times=times,
                    receipt_path=str(destination), replayed=False)
        return receipt

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
        self._verify_historical_inventory()
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
        if self.sdk_inventory_pending and op != 'trial_stop':
            raise Paused('SDK inventory click is still pending; observe and commit before another native request')
        if (self.historical_inventory_pending and not self._inventory_replan_current()
                and op not in {'guard', 'snapshot', 'scan', 'scan_trees', 'decision_screenshot',
                               'inventory_probe', 'trial_respawn', 'trial_stop'}):
            raise Paused('Retired SDK inventory permits defense and current review only; no material action sent')
        if 'inventory_confirm' in args:
            raise Paused('SDK inventory confirmation flag is owned by the exact trial bridge')
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
        sdk_click = op == 'slot_click' and state.get('menu', {}).get('type') in {'InventoryMenu', 'CraftingMenu'}
        if sdk_click or op == 'inventory_probe':
            if (state.get('kit_version') not in {'2026.10.7.8', '2026.10.7.9'}
                    or type(state.get('inventory_click_protocol')) is not int or state['inventory_click_protocol'] != 1):
                raise Paused('Server-confirmed trial inventory requires an audited host protocol 1; no click sent')
        if sdk_click:
            if not trial_auto_refill_ready(state):
                raise Paused('Trial SDK requires fresh .9 auto-refill cursor isolation; no click sent')
            inventory_menu_signature(state['menu'])
            args['inventory_confirm'] = True
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
        if request_id in self.historical_inventory_pending:
            raise Paused('Historical inventory request identifiers are forbidden; no replay')
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
        if sdk_click:
            record = {'protocol': 1, 'request_id': request_id, 'envelope': copy.deepcopy(envelope),
                      'arguments': copy.deepcopy(args), 'before': copy.deepcopy(state),
                      'outcome': 'sent_or_unknown_until_native_and_sdk_confirmation'}
            intent, unused = self._inventory_paths(request_id)
            self._durable_json(intent, record)
            self.sdk_inventory_pending[request_id] = record
        self.events('native_request', id=request_id, op=op, arguments=args)
        temp.replace(pending)
        self.active = request_id
        self.owned = True
        if op in MUTATING_OPS:
            self.pending_mutations[request_id] = {'id': request_id, 'op': op,
                'world_session': self.session, 'arguments': args}
            if sdk_click:
                self.pending_mutations[request_id].update(sdk_inventory_pending=True, intent_path=str(intent))
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
                if op == 'inventory_probe':
                    try:
                        if not path.exists() or current['control_revision'] != envelope['expected_revision']:
                            raise Paused('Inventory probe lacks a durable exact reply or current native revision')
                        native_inventory_probe_proof(result, envelope, state)
                    except Paused:
                        self.halted = True
                        raise
                    self.last_receipt = {**self.last_receipt, 'receipt_class': 'current_inventory_probe_only'}
                    self.receipts[-1] = self.last_receipt
                    self.last_inventory_probe = {'result': copy.deepcopy(result),
                                                 'envelope': copy.deepcopy(envelope), 'before': copy.deepcopy(state)}
                if op not in {'scan', 'scan_trees'} and result.get('phase') != 'done':
                    if (current['control_revision'] == envelope['expected_revision']
                            and guard_pre_dispatch_refusal(op, result, envelope['expected_revision'])):
                        if sdk_click:
                            intent, destination = self._inventory_paths(request_id)
                            self._durable_json(destination, {'protocol': 1, 'request_id': request_id,
                                'receipt_class': 'native_guard_busy_before_inventory_dispatch',
                                'intent_sha256': hashlib.sha256(intent.read_bytes()).hexdigest(),
                                'native_result': result, 'replayed': False})
                            self.sdk_inventory_pending.pop(request_id, None)
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
                    if (current['control_revision'] == envelope['expected_revision']
                            and confirmed_interaction_not_sent(op, result, args, envelope['expected_revision'])):
                        self.pending_mutations.pop(request_id, None)
                        self.last_receipt = {**self.last_receipt, 'code': 'pre_dispatch_refusal',
                                             'receipt_class': 'interaction_pre_dispatch_refusal'}
                        self.receipts[-1] = self.last_receipt
                        raise TrialInteractionRejected(args, self.last_receipt)
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
                if sdk_click:
                    try:
                        proof = native_inventory_click_proof(result, envelope, self.sdk_inventory_pending[request_id]['before'])
                        self.sdk_inventory_pending[request_id]['native_result'] = copy.deepcopy(result)
                        self._durable_json(self.root / 'trial-sdk-inventory' / 'native-results' / (request_id + '.json'), result)
                        if proof['classification'] == 'no_effect':
                            intent, destination = self._inventory_paths(request_id)
                            receipt = {'protocol': 1, 'request_id': request_id,
                                'receipt_class': 'server_processed_inventory_click_no_effect',
                                'intent_sha256': hashlib.sha256(intent.read_bytes()).hexdigest(),
                                'native_result': result, 'confirmation_scope': 'server_processed_no_inventory_transition',
                                'action_sent': True, 'sdk_predicate_confirmed': False, 'replayed': False}
                            self._durable_json(destination, receipt)
                            self.sdk_inventory_pending.pop(request_id)
                            self.pending_mutations.pop(request_id, None)
                            self.events('sdk_inventory_click_no_effect', id=request_id, action_sent=True,
                                        receipt_path=str(destination), replayed=False)
                            raise TrialInventoryNoEffect(args, receipt)
                    except TrialInventoryNoEffect:
                        raise
                    except (Paused, OSError, ValueError):
                        self.halted = True
                        raise
                elif result.get('phase') == 'done' and result.get('outcome_pending') is not True:
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
