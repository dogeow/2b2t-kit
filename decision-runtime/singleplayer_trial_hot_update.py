"""Replace only a paused Kit Python worker; keep the entered world and JVM.

Lifecycle requests go through the existing exact-world native API. Source is
verified before pausing and is installed only after the old worker has exited.
The trial directory, experience database and journals are never replaced.
"""
import argparse
import ast
import fcntl
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import uuid

from decisions import status
from singleplayer_trial_cli import call
from singleplayer_trial_bridge import (MUTATING_OPS, confirmed_mining_not_sent,
                                      canonical_save, validate_registry, validate_scope)
from survival_world import World, block_id, distance, shelter

SCHEMA = 1
REQUIRED = {'singleplayer_trial.py', 'singleplayer_trial_bridge.py',
            'singleplayer_experience.py', 'singleplayer_trial_cli.py',
            'singleplayer_trial_capabilities.py', 'singleplayer_trial_hot_update.py',
            'trial_surface_recovery.py'}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def point(value):
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(type(n) is int and abs(n) <= 30_000_000 for n in value)
            and -64 <= value[1] <= 320)


def same_save(value, expected):
    try:
        return canonical_save(value) == canonical_save(expected)
    except RuntimeError:
        return False


def checkpoint_from_skills(registry, state, skills, pending=None):
    return {'schema': SCHEMA, 'world_id': registry['world_id'], 'trial_id': registry['trial_id'],
            'world_name': registry['world_name'], 'source_run_id': registry.get('run_id'),
            'game_version': state.get('game_version'), 'observed_at': state.get('time'),
            'world_session': state.get('world_session'),
            'camp': skills.camp, 'stations': skills.stations, 'owned': skills.owned,
            'camp_completed': False,  # Always re-audit native blocks; never trust an old flag.
            'excluded': [list(p) for p in sorted(skills.excluded)],
            'explored': [list(p) for p in sorted(skills.explored)],
            'tried_grids': [list(p) for p in sorted(skills.tried_grids)],
            'station_anchor': skills.station_anchor,
            'rejected_routes': [[list(p) for p in route] for route in sorted(skills.rejected_routes)],
            'log_drops': skills.log_drops,
            'unresolved_native': list((pending or {}).values())}


def load_checkpoint(game, registry, state):
    """Coordinates may only be considered again inside this exact trial save."""
    root = Path(game) / 'config/twob2tkit/singleplayer-trial/worker'
    file = root / 'checkpoint.json'
    if file.is_file():
        if file.is_symlink() or file.stat().st_size > 2_000_000:
            raise RuntimeError('Invalid trial checkpoint file')
        value = json.loads(file.read_text())
        if (value.get('schema') != SCHEMA or not same_save(value.get('world_id'), registry['world_id'])
                or value.get('trial_id') != registry['trial_id']
                or value.get('game_version') != state.get('game_version')):
            return None
        return {**value, 'world_id': registry['world_id']}
    # The first upgrade predates checkpoints. Preserve the old observed camp
    # metadata, but not inventory, progress counters or any completion claim.
    legacy = root / 'bootstrap/status.json'
    if not legacy.is_file() or legacy.is_symlink() or legacy.stat().st_size > 2_000_000:
        return None
    value = json.loads(legacy.read_text())
    if not same_save(value.get('world_id'), registry['world_id']) or value.get('world_name') != registry['world_name']:
        return None
    return {'schema': SCHEMA, 'world_id': registry['world_id'], 'trial_id': registry['trial_id'],
            'world_name': registry['world_name'], 'source_run_id': registry.get('run_id'),
            'game_version': state.get('game_version'), 'observed_at': state.get('time'),
            'camp': value.get('camp'), 'stations': value.get('stations', {}),
            'owned': value.get('owned', {}), 'station_anchor': None,
            'excluded': [], 'explored': [], 'tried_grids': [], 'rejected_routes': [],
            'unresolved_native': [], 'source': 'legacy_native_bootstrap_metadata'}


def _receipt_safe(receipt, request):
    if (receipt.get('id') != request.get('id')
            or receipt.get('world_session') != request.get('world_session')
            or receipt.get('op') != request.get('op')):
        return False
    if receipt.get('phase') == 'done' and receipt.get('outcome_pending') is not True:
        return request['op'] != 'mine_block' or receipt.get('server_confirmed') is True
    return confirmed_mining_not_sent(request.get('op'), receipt, request.get('arguments', {}))


def unresolved_mutations(game, registry, state, checkpoint=None):
    automation = Path(game) / 'config/twob2tkit/automation'
    pending = {}
    if checkpoint:
        for row in checkpoint.get('unresolved_native', []):
            if isinstance(row, dict) and row.get('op') in MUTATING_OPS:
                pending[row.get('id')] = row
    mailbox = automation / 'request.json'
    if mailbox.is_file():
        request = json.loads(mailbox.read_text())
        if (request.get('local_trial') is True and same_save(request.get('world_id'), registry['world_id'])
                and request.get('trial_id') == registry['trial_id'] and request.get('op') in MUTATING_OPS):
            pending[request['id']] = {'id': request['id'], 'op': request['op'],
                'world_session': request.get('world_session'),
                'arguments': {'pos': request.get('pos')}}
    # Terminal native replies retain trial/run identity. A later read-only scan
    # must not hide an earlier unconfirmed mutation in the same run.
    for path in automation.glob('reply-trial-*.json'):
        if path.is_symlink() or path.stat().st_size > 2_000_000:
            continue
        reply = json.loads(path.read_text())
        identity = reply.get('trial_identity', {})
        if (identity.get('trial_id') == registry['trial_id'] and identity.get('run_id') == registry.get('run_id')
                and same_save(reply.get('world_id'), registry['world_id']) and reply.get('op') in MUTATING_OPS):
            pending[reply['id']] = {'id': reply['id'], 'op': reply['op'],
                'world_session': reply.get('world_session'),
                'arguments': {'pos': reply.get('mining_target')}}
    result = []
    for request_id, request in pending.items():
        if not isinstance(request_id, str) or not request_id or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in request_id):
            raise RuntimeError('Invalid unresolved native request identity')
        reply = automation / ('reply-' + request_id + '.json')
        if not reply.is_file() or reply.is_symlink() or not _receipt_safe(json.loads(reply.read_text()), request):
            result.append(request)
    return result


def restore_checkpoint(skills, checkpoint, registry, state):
    """Re-read actual station/camp blocks; old coordinates are only hypotheses."""
    if not checkpoint:
        return {'restored': False, 'reason': 'no_compatible_checkpoint'}
    if (checkpoint.get('schema') != SCHEMA or not same_save(checkpoint.get('world_id'), registry['world_id'])
            or checkpoint.get('trial_id') != registry['trial_id']
            or checkpoint.get('game_version') != state.get('game_version')):
        return {'restored': False, 'reason': 'different_trial_or_version'}
    unresolved = unresolved_mutations(skills.b.root.parents[2], registry, state, checkpoint)
    if unresolved:
        raise RuntimeError('Checkpoint has unconfirmed native mutations; preserve it for physical review')
    restored = {}
    for name, target in checkpoint.get('stations', {}).items():
        if name not in {'crafting_table', 'furnace'} or not point(target) or distance(state['pos'], target) > 32:
            continue
        result = skills.b.request('scan', min=target, max=target, details=True)
        row = next((r for r in result.get('blocks', []) if r.get('pos') == target), None)
        if row and block_id(row.get('state', '')) == name:
            skills.stations[name] = list(target)
            restored[name] = list(target)
    camp = checkpoint.get('camp')
    if point(camp) and distance(state['pos'], camp) <= 24:
        x, y, z = camp
        low, high = [x - 2, y - 1, z - 2], [x + 2, y + 2, z + 2]
        result = skills.b.request('scan', min=low, max=high, details=True)
        world = World(result.get('blocks', []), low, high)
        if world.stand(tuple(camp)) and all(world.full((px, y - 1, pz))
                for px in range(x - 2, x + 3) for pz in range(z - 2, z + 3)):
            skills.camp = list(camp)
            layout, door = shelter(camp)
            skills.camp_completed = all(world.earth(p) for p in layout) and world.name(door).endswith('_door')
    anchor = checkpoint.get('station_anchor')
    if point(anchor) and distance(state['pos'], anchor) <= 10:
        low, high = [anchor[0], anchor[1] - 1, anchor[2]], [anchor[0], anchor[1] + 1, anchor[2]]
        result = skills.b.request('scan', min=low, max=high, details=True)
        if World(result.get('blocks', []), low, high).stand(tuple(anchor)):
            skills.station_anchor = list(anchor)
    # Ownership only excludes old user construction from mining; it does not
    # assert a block exists or authorize rebuilding it.
    owned = checkpoint.get('owned', {})
    if isinstance(owned, dict) and len(owned) <= 4096:
        skills.owned = {key: value for key, value in owned.items()
                        if isinstance(key, str) and isinstance(value, str) and len(key) <= 64 and len(value) <= 96}
    skills.excluded = {tuple(p) for p in checkpoint.get('excluded', []) if point(p)}
    for name in ('explored', 'tried_grids'):
        values = checkpoint.get(name, [])
        setattr(skills, name, {tuple(p) for p in values[:256] if isinstance(p, list)
                              and len(p) == 2 and all(type(n) is int for n in p)})
    skills.rejected_routes = {tuple(tuple(p) for p in route)
                              for route in checkpoint.get('rejected_routes', [])[:256]
                              if isinstance(route, list) and len(route) <= 32 and all(point(p) for p in route)}
    drops = checkpoint.get('log_drops', {})
    if isinstance(drops, dict) and len(drops) <= 128:
        skills.log_drops = {identity: row for identity, row in drops.items()
                           if isinstance(identity, str) and isinstance(row, dict)
                           and isinstance(row.get('pos'), list) and len(row['pos']) == 3
                           and all(type(n) in (int, float) and math.isfinite(n) and abs(n) <= 30_000_000 for n in row['pos'])
                           and type(row.get('count')) is int and row['count'] > 0
                           and isinstance(row.get('item'), str) and row['item'].endswith('_log')
                           and type(row.get('observed_at')) is int
                           and 0 <= state.get('time', 0) - row['observed_at'] <= 240_000}
    return {'restored': True, 'stations_native_checked': sorted(restored),
            'camp_native_checked': skills.camp is not None,
            'camp_completed_native_checked': skills.camp_completed,
            'inventory_restored': False, 'native_request_replayed': False}


def install_and_restart(game, bundle, *, python=sys.executable, timeout=30,
                        reader=status, native=call, installer=None,
                        import_checker=None, worker_checker=None,
                        sleeper=time.sleep):
    # Release tooling is deliberately excluded from the installed worker. Keep
    # this import lazy so checkpoint restoration needs only bundled modules.
    from material_worker_release import verify, check_imports, install, worker_running
    installer = installer or install
    import_checker = import_checker or check_imports
    worker_checker = worker_checker or worker_running
    game, bundle = Path(game).resolve(), Path(bundle).resolve()
    root = game / 'config/twob2tkit/singleplayer-trial'
    automation = game / 'config/twob2tkit/automation'
    files = verify(bundle)
    if not REQUIRED.issubset(files):
        raise RuntimeError('Worker bundle lacks the trial lifecycle modules')
    for name in REQUIRED:
        ast.parse(files[name], filename=name)
    import_checker(bundle, python)
    bundle_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
    registry = validate_registry(json.loads((root / 'registry.json').read_text()), game)
    first = reader(automation)
    run = registry.get('run_id')
    validate_scope(first, registry, run_id=run)
    if first.get('singleplayer_trial_api_protocol') != 1 or first.get('trial_identity', {}).get('process_alive') is not True:
        raise RuntimeError('An existing native-owned trial worker is required')
    session = first['world_session']
    def safe(state, *, old_run=True, released=False):
        validate_scope(state, registry, session, run if old_run else None)
        if (state.get('health', 0) < 19 or state.get('food', 0) < 8
                or state.get('safety_hold', {}).get('active') is True
                or state.get('under_water') is True or state.get('screen')
                or any(state.get(k) for k in ('printing', 'chopping', 'navigating', 'borer_active', 'guard_busy'))):
            raise RuntimeError('Trial hot update requires healthy idle control; no health lock is changed')
        if released:
            keys = state.get('movement_keys', {})
            if (state.get('phase') == 'running' or not {'forward', 'back', 'jump', 'sneak'}.issubset(keys)
                    or any(value is not False for value in keys.values())):
                raise RuntimeError('Native owned inputs have not been confirmed released')
        return state
    safe(first)
    checkpoint = load_checkpoint(game, registry, first)
    if unresolved_mutations(game, registry, first, checkpoint):
        raise RuntimeError('Unconfirmed native mutation preserved; hot resume requires physical review')
    lock = (root / 'hot-update.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError('Another trial hot update is already running') from None
    proof = {'schema': 1, 'world_id': registry['world_id'], 'trial_id': registry['trial_id'],
             'before_run_id': run, 'world_session': session, 'bundle_sha256': bundle_hash,
             'minecraft_restarted': False, 'native_actions_replayed': False}
    try:
        paused = native(game, 'pause')
        if paused.get('trial_identity', {}).get('run_id') != run:
            raise RuntimeError('Native pause reply belongs to another run')
        until = time.monotonic() + timeout
        while True:
            current = safe(reader(automation))
            keys = current.get('movement_keys', {})
            if (current.get('time', 0) > first.get('time', 0) and current.get('phase') != 'running'
                    and {'forward', 'back', 'jump', 'sneak'}.issubset(keys)
                    and all(value is False for value in keys.values())):
                break
            if time.monotonic() >= until:
                raise RuntimeError('A fresh paused native snapshot was not observed')
            sleeper(.1)
        checkpoint = load_checkpoint(game, registry, current) or checkpoint
        if unresolved_mutations(game, registry, current, checkpoint):
            raise RuntimeError('Paused mutation is unconfirmed; preserve it and do not restart')
        if checkpoint:
            checkpoint['unresolved_native'] = []  # Cleared solely by exact native receipts above.
            atomic_json(root / 'worker/checkpoint.json', checkpoint)
        proof['pause_confirmed'] = True
        native(game, 'cancel')
        until = time.monotonic() + timeout
        while True:
            current = safe(reader(automation), old_run=False, released=True)
            if current.get('trial_identity', {}).get('process_alive') is False:
                break
            if time.monotonic() >= until:
                raise RuntimeError('Old native trial process is still alive; do not replace worker code')
            sleeper(.1)
        def running():
            current = safe(reader(automation), old_run=False, released=True)
            return current.get('trial_identity', {}).get('process_alive') is not False or worker_checker()
        proof['old_worker_exit_confirmed'] = True
        # Source replacement has its own stage/hash/backup/rollback behavior.
        proof['installation'] = installer(bundle, game, python=python, running=running)
        if hashlib.sha256(bundle.read_bytes()).hexdigest() != bundle_hash:
            raise RuntimeError('Worker artifact changed during installation; do not start it')
        safe(reader(automation), old_run=False, released=True)
        started = native(game, 'start')
        new_run = started.get('trial_identity', {}).get('run_id')
        if not isinstance(new_run, str) or not new_run or new_run == run:
            raise RuntimeError('New native worker run was not confirmed; do not replay Start')
        until = time.monotonic() + timeout
        while True:
            current = safe(reader(automation), old_run=False)
            identity = current.get('trial_identity', {})
            if identity.get('run_id') == new_run and identity.get('process_alive') is True:
                break
            if time.monotonic() >= until:
                raise RuntimeError('New worker process is unconfirmed; preserve Start and do not replay')
            sleeper(.1)
        proof.update(after_run_id=new_run, new_worker_native_confirmed=True,
                     checkpoint_preserved=checkpoint is not None,
                     experience_and_journals_replaced=False, native_completion_claimed=False)
        atomic_json(root / 'hot-update-proof.json', proof)
        return proof
    except Exception:
        atomic_json(root / 'hot-update-interrupted.json', {**proof, 'automatic_retry_allowed': False,
                    'resume_confirmed': False, 'detail': 'Preserve native requests and verify fresh state before another lifecycle command'})
        raise
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    args = parser.parse_args()
    print(json.dumps(install_and_restart(args.game, args.bundle, python=args.python), ensure_ascii=False))


if __name__ == '__main__':
    main()
