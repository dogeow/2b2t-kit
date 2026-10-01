"""Local Kit entry point for a bounded, already-watered potato field."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from job_progress import JobProgress
from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient, Handoff
from potato_farm import plan, run
from safety_interlock import require_unlocked

DEFAULT_GAME = Path('/Applications/.minecraft/versions/26.1.2')


def journal_directory(root, state, request, out=None):
    scope = {'server': state['server'].strip().lower().removesuffix(':25565'),
             'dimension': state['dimension'], 'layout': plan(request)}
    key = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
    registry = root/'farms'/key/'registry.json'
    default = registry.parent/'journal'
    if registry.exists():
        saved = json.loads(registry.read_text())
        if saved.get('scope') != scope or saved.get('world_session') != state['world_session']:
            raise RuntimeError('Saved farm belongs to another scope/world; explicit recovery is required')
        directory = Path(saved['directory'])
        if out is not None and directory != Path(out).resolve():
            raise RuntimeError('This farm already has a journal; changing output cannot bypass it')
    else:
        directory = Path(out).resolve() if out is not None else default.resolve()
        registry.parent.mkdir(parents=True, exist_ok=True)
        write_json(registry, {'scope': scope, 'world_session': state['world_session'],
                             'directory': str(directory)})
    return directory, directory/('potato-farm-'+key+'.json')


def normal_finish_allowed(c, state, result, book, hurt):
    lease = state.get('supervision_lease') or {}
    return bool(isinstance(result, dict)
                and (result.get('phase') == 'done' or result.get('code') == 'FARM_BATCH')
                and isinstance(book, dict) and not book.get('pending')
                and state.get('connected') is True and state.get('world_session') == c.world
                and state.get('control_revision') == c.rev and state.get('manual_movement') is False
                and state.get('screen') == '' and state.get('health') == 20
                and state.get('food', 0) >= 18 and state.get('recent_hurt_at') == hurt
                and state.get('guard_armed') is True and state.get('guard_busy') is False
                and lease.get('id') == c.heartbeat.id and lease.get('job_session') == c.task
                and lease.get('kind') == 'materials')


def finish_or_yield(c, result, journal, hurt, park_y, no_move):
    normal = False
    try:
        observed = c.status()
        book = json.loads(journal.read_text()) if journal.exists() else None
        normal = normal_finish_allowed(c, observed, result, book, hurt)
        if normal:
            if not no_move:
                park = [observed['pos'][0], park_y, observed['pos'][2]]
                c.checked('material_job_park', park_target=park); c.park_target = park
            c.finish()
            proof_path = Path(c.out)/'stock-safety.json'
            proof = json.loads(proof_path.read_text()) if proof_path.exists() else {}
            if proof.get('action') != 'KEEP_PVE_GUARD' or proof.get('lease') != c.heartbeat.id:
                raise RuntimeError('Farm work is preserved, but native guarded parking was not confirmed')
            return
        # Stop is permitted; movement and ordinary finish are not permitted
        # after injury, unknown use, changed control or another task's revision.
        if (observed.get('connected') and observed.get('world_session') == c.world
                and observed.get('control_revision') == c.rev
                and not observed.get('manual_movement') and observed.get('health', 0) >= 14):
            try: c.request('material_job_pause', release=False)
            except (RuntimeError, Handoff): pass
    except (RuntimeError, Handoff, OSError, ValueError):
        if normal: raise
        # Existing native protection/safety lock keeps responsibility. This
        # wrapper never unlocks, reconnects or fabricates a parked receipt.
        pass
    finally:
        c.heartbeat.close()
        if c.job_progress: c.job_progress.close()


def execute(game_dir, center, radius, max_cells, out=None, no_move=False):
    root = Path(game_dir)/'config/twob2tkit/automation'
    state = read_fresh(root); require_unlocked(root, state)
    if (not state.get('connected') or state.get('screen') or state.get('manual_movement')
            or state.get('dimension') != 'minecraft:overworld'
            or state.get('health') != 20 or state.get('food', 0) < 18):
        raise RuntimeError('A connected, idle, full-health Overworld player is required')
    request = {'authorized': True, 'center': center, 'radius': radius}
    directory, journal = journal_directory(root, state, request, out)
    if journal.exists():
        book = json.loads(journal.read_text())
        if book.get('world_session') != state['world_session'] or book.get('pending'):
            return {'phase': 'waiting', 'code': 'WAIT_RECONCILE', 'journal': str(journal),
                    'detail': 'Saved farm is unresolved; no control or repeated interaction sent'}
    park_y = min(315, max(100, state['pos'][1], center[1]+35))
    park = [state['pos'][0], park_y, state['pos'][2]]
    c = MaterialClient(root, directory/('control-'+str(time.time_ns())), server=state['server'],
                       remote_finish='guard', park_target=park)
    c.job_progress = JobProgress(root, c.world, c.task, c.rev, '土豆田', len(plan(request)['cells']))
    hurt = state['recent_hurt_at']
    result = None
    def checkpoint():
        observed = c.status()
        if observed['health'] != 20 or observed.get('food', 0) < 18 or observed['recent_hurt_at'] != hurt:
            raise RuntimeError('Work stopped for health/food; leave recovery to the safety guard')
        if journal.exists():
            book = json.loads(journal.read_text())
            c.set_progress(done=sum(row.get('planted') is True for row in book.get('cells', {}).values()),
                           phase='耕地与种植')
    def go(target):
        start = c.status()['pos']; pieces = max(1, math.ceil(math.dist(start, target)/24))
        for i in range(1, pieces+1):
            checkpoint(); point = [start[k]+(target[k]-start[k])*i/pieces for k in range(3)]
            c.checked('navigate', target=point, arrival=.25, seconds=40, air_only=True)
            if math.dist(c.status()['pos'], point) > .6:
                raise RuntimeError('Air route arrival was not observed; do not repeat')
    try:
        if not no_move:
            if math.hypot(state['pos'][0]-center[0]-.5, state['pos'][2]-center[2]-.5) > 32:
                raise RuntimeError('This pilot only handles a nearby field; approach within 32 blocks first')
            high = max(park_y, center[1]+35)
            scan = c.request('scan', min=center, max=[center[0], math.ceil(high)+2, center[2]], details=True)
            if (scan.get('world_session') != c.world or len(scan.get('blocks', [])) != 1
                    or scan['blocks'][0]['pos'] != center
                    or scan['blocks'][0]['state'] != 'Block{minecraft:water}[level=0]'):
                raise RuntimeError('An actual central water source and empty vertical column are required')
            go([state['pos'][0], high, state['pos'][2]])
            go([center[0]+.5, high, center[2]+.5])
            go([center[0]+.5, center[1]+1.6, center[2]+.5])
        checkpoint()
        result = run(c, request, directory, checkpoint, max_cells=max_cells)
        return result
    finally:
        finish_or_yield(c, result, journal, hurt, park_y, no_move)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir', type=Path, default=DEFAULT_GAME)
    parser.add_argument('--center', type=int, nargs=3, required=True, metavar=('X', 'Y', 'Z'))
    parser.add_argument('--radius', type=int, choices=(1, 2), default=2)
    parser.add_argument('--max-cells', type=int, choices=range(1, 25), default=24)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--no-move', action='store_true', help='Use current position; no approach movement')
    args = parser.parse_args(argv)
    try:
        result = execute(args.game_dir, args.center, args.radius, args.max_cells, args.out, args.no_move)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get('phase') == 'done' or result.get('code') == 'FARM_BATCH' else 2
    except (RuntimeError, ValueError, OSError, KeyError) as error:
        print(json.dumps({'phase': 'waiting', 'code': 'WAIT_CONTROL', 'detail': str(error)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
