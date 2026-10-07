"""Explicit physical replanning after an older controller has actually ended.

An unknown historical chop is never completed or replayed here. A reviewed
normal stop/save and a new live physical baseline permit independent work in
the current exact trial. This module neither starts a controller nor unlocks
another game mode. Model output cannot submit this operator review.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

from singleplayer_trial_bridge import Paused, canonical_save, complete_scan, validate_scope

ARTIFACTS = frozenset({'native_before_pause', 'native_pause_request', 'native_pause_reply',
    'native_after_pause', 'before_save', 'after_save', 'normal_quit_reply', 'normal_exit',
    'backup_diff', 'backup_before', 'backup_after'})
SAFE_ID = re.compile(r'rebaseline-[a-zA-Z0-9_-]{1,74}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')


def pid_alive(pid):
    if type(pid) is not int or pid <= 1:
        return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True


def file_hash(path):
    path = Path(path)
    if (not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents))
            or not path.is_file()):
        raise Paused('Physical review evidence must be an existing absolute unlinked file')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(131072), b''):
            digest.update(data)
    return digest.hexdigest()


def artifact(reference, *, text=False, maximum=2_000_000):
    if (not isinstance(reference, dict) or not isinstance(reference.get('path'), str)
            or not isinstance(reference.get('sha256'), str) or not SHA.fullmatch(reference['sha256'])
            or file_hash(reference['path']) != reference['sha256']):
        raise Paused('Physical review evidence hash differs; preserve all old records')
    path = Path(reference['path'])
    if path.stat().st_size > maximum:
        raise Paused('Physical review record exceeds its bounded size')
    value = path.read_text()
    return value if text else json.loads(value)


def exact_trial(value, world, trial, run=None):
    identity = value.get('trial_identity', {})
    return (isinstance(identity, dict) and canonical_save(identity.get('world_id')) == world
        and identity.get('trial_id') == trial
        and (run is None or identity.get('run_id') == run))


def stopped_children(state):
    keys = state.get('movement_keys', {})
    return (all(state.get(k) is False for k in ('chopping', 'navigating', 'borer_active', 'printing'))
        and state.get('phase') != 'running' and isinstance(keys, dict)
        and {'forward', 'back', 'jump', 'sneak'} <= keys.keys()
        and all(v is False for v in keys.values()))


def _validate_review(worker, request, state, *, pid_alive=pid_alive, now_ms=None):
    """Verify this bounded operator request, real terminal evidence and old bytes."""
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    worker.check_legacy_evidence()
    validate_scope(state, worker.registry, worker.bridge.session, worker.run_id)
    if (not isinstance(request, dict) or request.get('schema') != 1
            or request.get('kind') != 'fresh_material_replan'
            or not isinstance(request.get('id'), str) or not SAFE_ID.fullmatch(request['id'])
            or any(request.get(k) != v for k, v in {
                'world_id': worker.registry['world_id'], 'trial_id': worker.registry['trial_id'],
                'run_id': worker.run_id, 'world_session': state['world_session'],
                'dimension': state['dimension'], 'expected_revision': state['control_revision']}.items())
            or any(type(request.get(k)) is not int for k in ('created_at', 'expires_at', 'expected_revision'))
            or not request['created_at'] <= now_ms <= request['expires_at']
            or not 0 < request['expires_at'] - request['created_at'] <= 120_000):
        raise Paused('Physical rebaseline request scope or validity window differs')
    if (not worker.legacy_pending or worker.bridge.halted or worker.bridge.pending_mutations
            or worker.bridge.active is not None or not stopped_children(state)
            or state.get('trial_identity', {}).get('process_alive') is not True
            or state.get('guard_busy') is True or state.get('screen')
            or state.get('control_revision') != worker.bridge.revision
            or state.get('last_request', '') != worker.bridge.last
            or state.get('game_version') != '26.1.2' or state.get('dimension') != 'minecraft:overworld'
            or state.get('safety_hold', {}).get('active') is not False
            or state.get('safety_hold', {}).get('escaping') is not False
            or type(state.get('time')) is not int or not 0 <= now_ms - state['time'] <= 3000):
        raise Paused('Current physical review controller is not fresh, alive and idle')
    # This admission is intentionally only the audited old chopping case.
    # Unknown inventory transactions or current-run actions need their own
    # exact reconciliation and cannot borrow this historical-stop permission.
    chops = [row for row in worker.legacy_pending if row.get('op') == 'chop']
    inventory = [row for row in worker.legacy_pending if row.get('op') == 'slot_click']
    if len(chops) != 1 or len(inventory) > 1 or len(worker.legacy_pending) != len(chops) + len(inventory):
        raise Paused('Only the stopped historical chop and separately reviewed inventory case are supported')
    if inventory:
        from trial_inventory_audit import validate_inventory_review
        validate_inventory_review(worker, request.get('inventory_review'), state, pid_alive)
    elif request.get('inventory_review') is not None:
        raise Paused('Inventory review differs from the preserved historical intents')
    old = chops[0]
    if old.get('run_id') == worker.run_id or old.get('world_session') == state['world_session']:
        raise Paused('Old controller still shares the current run or world session')
    archive = worker.output / 'legacy-material-intents' / (old['id'] + '.request.json')
    # A previous process may already have preserved the full envelope before
    # a new guard replaced the mailbox. protect_legacy_evidence then has only
    # the three root records; the absence of a matching mailbox must not omit
    # that existing immutable envelope from this request's canonical set.
    frozen = {str(path): digest for path, digest in (worker.legacy_evidence or {}).items()}
    archive_hash = file_hash(archive)
    if str(archive) in frozen and frozen[str(archive)] != archive_hash:
        raise Paused('Archived historical envelope changed after freezing')
    frozen[str(archive)] = archive_hash
    if (not worker.legacy_evidence or request.get('frozen_legacy') != frozen
            or any(value is None for value in frozen.values())):
        raise Paused('Physical review does not bind the exact frozen legacy evidence')
    original = json.loads(archive.read_text())
    if (any(original.get(k) != old.get(k) for k in
            ('id', 'op', 'world_id', 'trial_id', 'run_id', 'world_session', 'dimension'))
            or type(original.get('expires_at')) is not int or original['expires_at'] >= now_ms):
        raise Paused('Historical request is unexpired or differs from its frozen full envelope')
    report = artifact(request.get('report'))
    if (not isinstance(report, dict) or report.get('schema') != 1
            or report.get('kind') != 'operator_physical_review'
            or report.get('decision') != 'fresh_replan_allowed'
            or report.get('historical_effects_unresolved') is not True
            or any(report.get(k) != v for k, v in {
                'old_request_id': old['id'], 'world_id': worker.registry['world_id'],
                'trial_id': worker.registry['trial_id'], 'old_run_id': old['run_id'],
                'old_world_session': old['world_session']}.items())
            or any(type(report.get(k)) is not int or report[k] <= 1
                   for k in ('old_worker_pid', 'old_jvm_pid'))
            or report['old_worker_pid'] == os.getpid() or report['old_jvm_pid'] == worker.parent_pid
            or pid_alive(report['old_worker_pid']) or pid_alive(report['old_jvm_pid'])):
        raise Paused('Physical review lacks a separately terminated historical controller')
    refs = report.get('artifacts')
    if not isinstance(refs, dict) or set(refs) != ARTIFACTS:
        raise Paused('Physical review lacks the real pause, quit, save and backup artifacts')
    records = {key: artifact(ref) for key, ref in refs.items()
               if key not in {'backup_before', 'backup_after'}}
    for key in ('backup_before', 'backup_after'):
        if file_hash(refs[key]['path']) != refs[key].get('sha256'):
            raise Paused('Physical world archive changed after operator review')
    before, after = records['native_before_pause'], records['native_after_pause']
    pause, receipt = records['native_pause_request'], records['native_pause_reply']
    world, trial = worker.registry['world_id'], worker.registry['trial_id']
    if (not exact_trial(before, world, trial, old['run_id'])
            or before.get('world_session') != old['world_session'] or before.get('id') != old['id']
            or before.get('game_version') != state.get('game_version')
            or before.get('op') != 'chop' or before.get('phase') != 'running'
            or before.get('chopping') is not True
            or pause.get('protocol') != 1 or pause.get('command') != 'pause'
            or pause.get('world_id') != world or pause.get('world_session') != old['world_session']
            or type(pause.get('expected_revision')) is not int
            or pause['expected_revision'] != before.get('control_revision')
            or receipt.get('protocol') != 1 or receipt.get('phase') != 'done'
            or receipt.get('id') != pause.get('id')
            or not exact_trial(receipt, world, trial, old['run_id'])
            or not exact_trial(after, world, trial)
            or after.get('world_session') != old['world_session'] or after.get('id') != old['id']
            or not stopped_children(after) or after.get('chopper_remaining') != 0
            or after.get('chopper_platforms') != 0
            or after.get('trial_identity', {}).get('process_alive') is not False
            or after.get('trial_identity', {}).get('run_id') not in ('', old['run_id'])
            or type(before.get('time')) is not int or type(after.get('time')) is not int
            or after['time'] < before['time']):
        raise Paused('Native pause receipt does not prove this historical child actually stopped')
    saved, disconnected, quit_reply = (records[k] for k in ('before_save', 'after_save', 'normal_quit_reply'))
    if (not exact_trial(saved, world, trial) or saved.get('world_id') != world
            or not stopped_children(saved) or saved.get('trial_identity', {}).get('process_alive') is not False
            or disconnected.get('connected') is not False or not exact_trial(disconnected, world, trial)
            or disconnected.get('trial_identity', {}).get('process_alive') is not False
            or quit_reply.get('protocol') != 1 or quit_reply.get('phase') != 'done'
            or not exact_trial(quit_reply, world, trial)
            or quit_reply.get('trial_identity', {}).get('process_alive') is not False):
        raise Paused('Normal quit lacks the stopped save and disconnected native observations')
    exit_observation = records['normal_exit']
    log = artifact(exit_observation.get('save_log'), text=True)
    if (exit_observation.get('schema') != 1
            or exit_observation.get('source') != 'operator_verified_native_quit_and_launcher_observation'
            or type(exit_observation.get('exit_code')) is not int or exit_observation['exit_code'] != 0
            or exit_observation.get('exit_type') != 'NORMAL'
            or exit_observation.get('old_jvm_alive_now') is not False
            or exit_observation.get('old_jvm_pid') != report['old_jvm_pid']
            or type(exit_observation.get('observed_at')) is not int
            or not after['time'] <= exit_observation['observed_at'] < request['created_at']
            or not all(s in log for s in ('Saving players', 'Saving worlds',
                '(world): All chunks are saved', '(DIM-1): All chunks are saved',
                '(DIM1): All chunks are saved', 'All dimensions are saved'))):
        raise Paused('Operator-observed normal exit lacks matching complete saved-world evidence')
    diff = records['backup_diff']
    worlds, chunks = diff.get('worlds'), diff.get('chunks')
    if (diff.get('schema') != 1 or diff.get('mode') != 'read_only_saved_world_diff'
            or diff.get('request_id') != old['id'] or diff.get('run_id') != old['run_id']
            or diff.get('request_world_session') != old['world_session']
            or not isinstance(worlds, list) or len(worlds) != 2
            or any(not isinstance(v, dict) for v in worlds)
            or [v.get('sha256') for v in worlds] != [refs[k]['sha256'] for k in ('backup_before', 'backup_after')]
            or any(type(v.get('last_played_ms')) is not int for v in worlds)
            or not worlds[0]['last_played_ms'] < before['time'] <= after['time'] <= worlds[1]['last_played_ms']
            or not isinstance(chunks, list) or not chunks
            or any(not isinstance(v, dict) for v in chunks)
            or any(type(v.get('checked_blocks')) is not int or v['checked_blocks'] != 98_304 for v in chunks)
            or sum(v['checked_blocks'] for v in chunks) != diff.get('checked_blocks')):
        raise Paused('Physical backup comparison is absent, partial or not bound to this stopped action')
    # Extend only the in-memory freeze after this exact full old scope and
    # all actual terminal/save evidence have passed. Old files remain intact.
    worker.legacy_evidence[archive] = archive_hash
    return {'request': request, 'report': report, 'report_sha256': request['report']['sha256'],
            'verified_at': now_ms}


def validate_review(worker, request, state, *, pid_alive=pid_alive, now_ms=None):
    try:
        return _validate_review(worker, request, state, pid_alive=pid_alive, now_ms=now_ms)
    except Paused:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise Paused('Physical operator review contains missing or malformed real evidence') from None


def inventory_baseline(state):
    rows = state.get('inventory')
    if not isinstance(rows, list) or len(rows) > 43:
        raise Paused('Physical inventory snapshot is partial or malformed')
    slots = {}
    for row in rows:
        if (not isinstance(row, dict) or type(row.get('slot')) is not int or not 0 <= row['slot'] < 43
                or row['slot'] in slots or not isinstance(row.get('item'), str)
                or not row['item'].startswith('minecraft:') or type(row.get('count')) is not int
                or type(row.get('max_stack')) is not int or not 1 <= row['max_stack'] <= 99
                or not 0 <= row['count'] <= row['max_stack']
                or (row['item'] == 'minecraft:air') != (row['count'] == 0)):
            raise Paused('Physical inventory snapshot is partial or malformed')
        slots[row['slot']] = row
    if not set(range(36)) <= slots.keys():
        raise Paused('Physical inventory snapshot lacks the complete 36 backpack slots')
    menu = state.get('menu', {})
    cells = menu.get('slots')
    if (state.get('inventory_cursor_precondition_protocol') != 1
            or state.get('inventory_isolation', {}).get('supported') is not True
            or state.get('inventory_isolation', {}).get('active') is not True
            or menu.get('id') != 0 or menu.get('type') != 'InventoryMenu'
            or menu.get('cursor', {}).get('item') != 'minecraft:air'
            or menu.get('cursor', {}).get('count') != 0
            or not isinstance(cells, list) or len(cells) < 5
            or any(not isinstance(cells[i], dict) or cells[i].get('slot') != i
                   or cells[i].get('item') != 'minecraft:air' or cells[i].get('count') != 0
                   for i in range(5))):
        raise Paused('Physical rebaseline requires the real empty SDK cursor and inventory grid')
    return [slots[i] for i in sorted(slots)]


def capture_baseline(worker, verified_review, *, now_ms=None):
    """Read the real inventory and request one bounded complete current Kit scan."""
    before = worker.bridge.read()
    clock = (lambda: int(time.time() * 1000)) if now_ms is None else lambda: now_ms
    checked = validate_review(worker, verified_review['request'], before, now_ms=clock())
    stock = inventory_baseline(before)
    x, y, z = (math.floor(n) for n in before['pos'])
    bounds = {'min': [x - 10, max(-64, y - 6), z - 10],
              'max': [x + 10, min(319, y + 6), z + 10], 'details': True}
    terrain = worker.bridge.request('scan', **bounds)
    after = worker.bridge.read()
    validate_review(worker, checked['request'], after, now_ms=clock())
    if (not complete_scan(terrain, bounds, before['control_revision'])
            or terrain.get('world_session') != before['world_session']
            or math.dist(before['pos'], after['pos']) > .25
            or inventory_baseline(after) != stock):
        raise Paused('Physical baseline scan, position or inventory changed; no material work admitted')
    # TrialWorld normally trusts complete sparse snapshots. Validate each
    # positive cell here too, so malformed/unloaded evidence cannot define air.
    seen = set()
    for row in terrain['blocks']:
        point = row.get('pos') if isinstance(row, dict) else None
        if (not isinstance(point, list) or len(point) != 3 or any(type(n) is not int for n in point)
                or tuple(point) in seen or not all(bounds['min'][i] <= point[i] <= bounds['max'][i] for i in range(3))
                or not isinstance(row.get('state'), str)
                or any(type(row.get(k)) is not bool for k in ('solid', 'fluid', 'block_entity', 'passable'))):
            raise Paused('Physical baseline terrain contains malformed or duplicate evidence')
        seen.add(tuple(point))
    return {'schema': 1, 'source': 'fresh_kit_physical_baseline',
        'request_id': checked['request']['id'], 'newbaseline_id': 'baseline-' + uuid.uuid4().hex,
        **{k: after[k] for k in ('world_id', 'world_session', 'dimension', 'control_revision')},
        'trial_id': worker.registry['trial_id'], 'run_id': worker.run_id, 'observed_at': after['time'],
        'inventory': stock, 'menu': after['menu'], 'position': after['pos'],
        'terrain': terrain, 'scan_bounds': bounds, 'review': checked,
        'historical_effects_unresolved': True, 'legacy_pending': worker.legacy_pending,
        'forbidden_request_ids': [row['id'] for row in worker.legacy_pending],
        'old_action_replayed': False, 'old_action_completed': False}


def recapture_after_respawn(worker, baseline, receipt):
    """Only an acknowledged same-run normal respawn may renew physical facts.

    This inherits the already admitted operator review, never a new decision
    from a model. The original historical evidence and outcome stay intact.
    A hand-opened save or an unknown current operation cannot use this path.
    """
    state = worker.bridge.read()
    if (not isinstance(baseline, dict) or baseline.get('source') != 'fresh_kit_physical_baseline'
            or baseline.get('run_id') != worker.run_id
            or baseline.get('trial_id') != worker.registry['trial_id']
            or baseline.get('world_id') != worker.registry['world_id']
            or not isinstance(receipt, dict) or receipt != worker.bridge.last_receipt
            or receipt.get('native') is not True or receipt.get('phase') != 'done'
            or receipt.get('op') != 'trial_respawn'
            or receipt.get('request_id') != worker.bridge.last
            or receipt.get('id') != worker.bridge.last or receipt.get('last_request') != worker.bridge.last
            or receipt.get('world_session') != state['world_session']
            or receipt.get('control_revision') != state['control_revision']
            or not exact_trial(receipt, worker.registry['world_id'], worker.registry['trial_id'], worker.run_id)
            or worker.bridge.active is not None or worker.bridge.pending_mutations or worker.bridge.halted):
        raise Paused('Physical baseline renewal requires this run\'s exact acknowledged normal respawn')
    now = int(time.time() * 1000)
    request = dict(baseline['review']['request'])
    request.update(id='rebaseline-respawn-' + uuid.uuid4().hex,
                   world_session=state['world_session'], expected_revision=state['control_revision'],
                   created_at=now, expires_at=now + 120_000)
    reviewed = validate_review(worker, request, state)
    result = capture_baseline(worker, reviewed)
    result.update(renewal_source='acknowledged_same_run_normal_respawn',
                  previous_baseline_id=baseline['newbaseline_id'], native_respawn_receipt=receipt)
    return result


def review_receipt_path(output, request_id):
    if not isinstance(request_id, str) or not SAFE_ID.fullmatch(request_id):
        raise Paused('Malformed physical review identity; preserve its request')
    return Path(output) / 'rebaseline-receipts' / (request_id + '.json')


def rejected_review_receipt(output, request, content):
    """Only the exact worker-recorded terminal refusal permits replacement."""
    path = review_receipt_path(output, request.get('id'))
    if not path.exists():
        return None
    receipt = artifact({'path': str(path), 'sha256': file_hash(path)}, maximum=131072)
    if (not isinstance(receipt, dict) or receipt.get('schema') != 1
            or receipt.get('source') != 'kit_worker_physical_review_refusal'
            or receipt.get('phase') != 'rejected' or receipt.get('id') != request['id']
            or receipt.get('request_sha256') != hashlib.sha256(content).hexdigest()
            or receipt.get('request_admitted') is not False
            or receipt.get('material_macros_executed') is not False
            or any(receipt.get(k) != request.get(k) for k in
                   ('world_id', 'trial_id', 'run_id', 'world_session'))):
        raise Paused('Physical review receipt differs or is not a terminal unadmitted refusal')
    return receipt


def record_review_refusal(worker, request, content, reason):
    """Write a new review receipt, never a host reply or a historical intent."""
    path = review_receipt_path(worker.output, request.get('id'))
    existing = rejected_review_receipt(worker.output, request, content)
    if existing is not None:
        return existing
    if any(p.is_symlink() for p in path.parents):
        raise Paused('Physical review receipt directory must not contain symlinks')
    value = {'schema': 1, 'source': 'kit_worker_physical_review_refusal',
        'id': request['id'], 'phase': 'rejected', 'time': int(time.time() * 1000),
        **{k: request.get(k) for k in ('world_id', 'trial_id', 'run_id', 'world_session')},
        'worker_run_id': worker.run_id, 'worker_pid': os.getpid(),
        'request_sha256': hashlib.sha256(content).hexdigest(), 'reason': str(reason)[:512],
        'request_admitted': False, 'material_macros_executed': False,
        'historical_effects_unresolved': True, 'old_action_replayed': False}
    from singleplayer_trial_hot_update import atomic_json
    atomic_json(path, value)
    return value


def submit_review(game, report_path, *, expires_seconds=120, inventory_review=None):
    """CLI operator entry. The worker still verifies and captures its own facts."""
    from decisions import status
    game = Path(game).resolve()
    root = game / 'config/twob2tkit/singleplayer-trial'
    worker = json.loads((root / 'worker/status.json').read_text())
    current = status(root.parent / 'automation')
    registry = json.loads((root / 'registry.json').read_text())
    if type(expires_seconds) is not int or not 1 <= expires_seconds <= 120:
        raise Paused('Physical review request validity must be 1..120 seconds')
    if (worker.get('legacy_material_review') is not True or worker.get('material_macros_enabled') is not False
            or worker.get('run_id') != registry.get('run_id')
            or current.get('trial_identity', {}).get('run_id') != registry.get('run_id')):
        raise Paused('An exact live legacy-review worker is required before submission')
    report_path = Path(report_path).resolve()
    # Take hashes of the original records and exact archived full envelope;
    # this is a new request, never a rewrite of the old unknown action.
    output = root / 'worker'
    frozen = {str(path): file_hash(path) for path in
        (output / 'checkpoint.json', output / 'journal.jsonl', output / 'bootstrap/status.json')}
    for row in worker.get('legacy_pending', []):
        rid = row.get('id')
        if not isinstance(rid, str) or not re.fullmatch(r'trial-[A-Za-z0-9_-]{1,74}', rid):
            raise Paused('Malformed historical native identity; no rebaseline request written')
        path = output / 'legacy-material-intents' / (rid + '.request.json')
        frozen[str(path)] = file_hash(path)
    if inventory_review is not None:
        from trial_inventory_audit import historical_pending
        extra, protected = historical_pending(output, registry, current)
        if len(extra) != 1:
            raise Paused('One separately archived historical inventory case is required')
        frozen.update({str(path): digest for path, digest in protected.items()})
    now = int(time.time() * 1000)
    value = {'schema': 1, 'kind': 'fresh_material_replan', 'id': 'rebaseline-' + uuid.uuid4().hex,
        'world_id': registry['world_id'], 'trial_id': registry['trial_id'], 'run_id': registry['run_id'],
        **{k: current[k] for k in ('world_session', 'dimension')},
        'expected_revision': current['control_revision'], 'created_at': now,
        'expires_at': now + expires_seconds * 1000,
        'report': {'path': str(report_path), 'sha256': file_hash(report_path)}, 'frozen_legacy': frozen}
    if inventory_review is not None:
        inventory_review = Path(inventory_review).resolve()
        value['inventory_review'] = {'path': str(inventory_review), 'sha256': file_hash(inventory_review)}
    path = output / 'rebaseline-request.json'
    if path.exists() or path.is_symlink():
        if path.is_symlink() or path.stat().st_size > 131072:
            raise Paused('Invalid existing physical review request; preserve it')
        content = path.read_bytes()
        previous = json.loads(content)
        if not isinstance(previous, dict) or rejected_review_receipt(output, previous, content) is None:
            raise Paused('A physical rebaseline request already exists; preserve it and inspect its receipt')
        folder = output / 'rejected-rebaseline-requests'
        if any(p.is_symlink() for p in (folder, *folder.parents)):
            raise Paused('Physical review archive must not contain symlinks')
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / (previous['id'] + '.json')
        if destination.exists() or destination.is_symlink():
            raise Paused('Rejected review archive exists; never overwrite it')
        # Move this exact terminally rejected new review, not an old Minecraft
        # action. Reissue uses a fresh scope/ID and leaves both records intact.
        path.replace(destination)
        value['supersedes_rejected_request'] = {'id': previous['id'], 'path': str(destination),
            'sha256': hashlib.sha256(content).hexdigest(),
            'receipt_path': str(review_receipt_path(output, previous['id']))}
    from singleplayer_trial_hot_update import atomic_json
    atomic_json(path, value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expires-seconds', type=int, default=120)
    parser.add_argument('--inventory-review', type=Path)
    args = parser.parse_args()
    print(json.dumps(submit_review(args.game, args.report, expires_seconds=args.expires_seconds,
        inventory_review=args.inventory_review), ensure_ascii=False))


if __name__ == '__main__':
    main()
