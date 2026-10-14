"""Reach one current-world cache hint and read bounded live geology; never mine."""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import MaterialClient, Handoff
from . import bobby_snow_cache as cache, bobby_snow_route as route
from .cached_tree_source import outside_protected
from .navigation import lift_for_travel, local_park, settled_state
from .profile import load
from .recovery_continuation import WaitingIntent
from .stationary_resume import StationaryResume
import time
import uuid
import re


def rejected_unowned_admission(root, attempt, ready):
    """Retry only a proved rejected startup, never a missing/unknown receipt."""
    current = read_fresh(root)
    if (current.get('supervision_lease') or current.get('world_session') != ready.get('world_session')
            or current.get('control_revision') != ready.get('control_revision')):
        return False
    try:
        path = Path(root)/'request.json'
        if path.stat().st_size > 100_000:return False
        req = json.loads(path.read_text()); rid = req.get('id'); task = req.get('task_session')
        if (not isinstance(rid,str) or not re.fullmatch(r'materials-[0-9a-f]{12}',rid)
                or not isinstance(task,str) or not re.fullmatch(r'materials-[0-9a-f]{16}',task)
                or req.get('op') != 'material_session' or current.get('last_request') != rid):
            return False
        reply_path = Path(root)/('reply-'+rid+'.json')
        manifest_path = Path(attempt)/'control'/('run-manifest-'+task+'.json')
        if reply_path.stat().st_size > 2_000_000 or manifest_path.stat().st_size > 100_000:return False
        reply = json.loads(reply_path.read_text()); manifest = json.loads(manifest_path.read_text())
        return (reply.get('id') == rid and reply.get('phase') == 'error'
                and reply.get('detail') == 'Material session cannot acquire control'
                and not reply.get('supervision_lease') and manifest.get('task_session') == task
                and all(d.get('world_session') == ready.get('world_session') for d in (req,reply,manifest))
                and req.get('expected_revision') == ready.get('control_revision')
                and reply.get('control_revision') == ready.get('control_revision'))
    except (OSError,ValueError,TypeError):
        return False


def wait_ready(root, request, out):
    """Use existing stationary permission; no native request is sent while waiting."""
    first = read_fresh(root)
    world = first['world_session']; revision = first['control_revision']
    original = {**request, 'id': 'geology-wait-'+uuid.uuid4().hex[:12],
                'created_at': first['time'], 'context': {**request['context'],
                    'world_session': world, 'expected_revision': revision, 'start_pos': first['pos']}}
    waiting = WaitingIntent(original, out)
    lease = first.get('supervision_lease') or {}
    if (lease.get('kind') == 'parking' and lease.get('world_session') == world
            and lease.get('revision') == revision and lease.get('job_session')):
        waiting.state['native_task_session'] = lease['job_session']
    watch = StationaryResume(root)
    while True:
        current = read_fresh(root)
        if current.get('world_session') != world:
            raise RuntimeError('Survey waiting world changed; no native request sent')
        if (current.get('detail') == '工具箱停止全部'
                and current.get('control_revision', revision) > revision):
            raise RuntimeError('New user stop-all received; survey wait ended')
        if current.get('health') == 20 and current.get('food', 0) >= 18 and watch.poll(waiting):
            return current
        time.sleep(.25)


def slices(candidate, low_y, high_y):
    tile = candidate.get('tile')
    if (not isinstance(tile, list) or len(tile) != 2 or any(type(v) is not int for v in tile)
            or type(low_y) is not int or type(high_y) is not int
            or not -64 <= low_y <= high_y <= 319):
        raise ValueError('Survey requires one complete cache tile and valid world heights')
    x, z = tile
    return [([x, y, z], [x+15, min(high_y, y+63), z+15])
            for y in range(low_y, high_y+1, 64)]


def run(root, request, candidate, low_y, high_y, out, biomes):
    boxes = slices(candidate, low_y, high_y)
    root = Path(root); out = Path(out); out.mkdir(exist_ok=False)
    first = read_fresh(root)
    if (not first.get('connected') or first.get('health') != 20 or first.get('food', 0) < 18
            or first.get('screen') or first.get('manual_movement')
            or first.get('projection_selection', {}).get('key') != request['projection_key']
            or first.get('server', '').removesuffix(':25565') != request['context']['server'].removesuffix(':25565')
            or first.get('dimension') != request['context']['dimension']):
        raise RuntimeError('Authorized survey scope or current healthy control differs')
    profile = load(root, first)
    if not outside_protected(candidate, profile.get('protected_regions', [])+[first['projection_selection']]):
        raise RuntimeError('Survey hint overlaps a protected construction footprint')
    game = root.parents[2]
    if not cache.validate_candidate(game, first['server'], first['dimension'], candidate, biome_filter=biomes):
        raise RuntimeError('Current-world geology cache hint is no longer valid')
    c = MaterialClient(root, out/'control', server=first['server'], remote_finish='guard',
                       park_target=[first['pos'][0], min(315, first['pos'][1]+24), first['pos'][2]])
    world = c.world
    report = {'world_session': world, 'candidate': route.public_candidate(candidate),
              'source_survey_only': True, 'inventory_credit': 0, 'scans': []}
    ledger = {}; route_path = out/'resource-route.json'
    def checkpoint():
        state = c.status()
        if (state.get('world_session') != world or state.get('health', 0) < 19
                or state.get('food', 0) < 18 or state.get('projection_selection', {}).get('key') != request['projection_key']):
            raise RuntimeError('Geology survey world, map or healthy control changed')
        return state
    try:
        write_json(out/'intent.json', report)
        lift_for_travel(c); c.set_progress(phase='核验材料产地')
        route.outbound(c, candidate, first['server'], first['dimension'], route_path, ledger, checkpoint,
                       lambda v: cache.validate_candidate(game, first['server'], first['dimension'], v, biome_filter=biomes),
                       lambda v: cache.validate_current_world(game, first['server'], first['dimension'], v))
        counts = Counter()
        for index, (low, high) in enumerate(boxes):
            checkpoint(); reply = c.checked('scan', min=low, max=high, details=True)
            total = math.prod(high[i]-low[i]+1 for i in range(3))
            if (reply.get('id') != c.last or reply.get('world_session') != world
                    or reply.get('unloaded_chunks', 0) or reply.get('scan_cells_read') != total
                    or reply.get('scan_total_cells') != total):
                raise RuntimeError('Current geology scan is incomplete; no source registered')
            seen = set()
            for row in reply.get('blocks', []):
                p = row.get('pos')
                if (not isinstance(p, list) or len(p) != 3 or any(type(v) is not int for v in p)
                        or tuple(p) in seen or not all(low[i] <= p[i] <= high[i] for i in range(3))):
                    raise RuntimeError('Geology scan contains duplicate or outside cells')
                seen.add(tuple(p)); counts[row['state'].split('}', 1)[0].removeprefix('Block{')] += 1
            name = 'live-scan-%02d.json' % index; write_json(out/name, reply)
            report['scans'].append({'path': name, 'min': low, 'max': high, 'cells': total})
            write_json(out/'progress.json', report)
        report.update(complete=True, counts=dict(counts), actual_observed_at=checkpoint()['time'])
        write_json(out/'result.json', report); return report
    finally:
        try:
            if c.native_inflight is None and not getattr(c, 'unconfirmed_native_request', None):
                point = local_park(c)
                c.checked('navigate', target=point, arrival=.25, air_only=True, seconds=90)
                state = settled_state(c, point, .55); point = [state['pos'][0], state['pos'][1]+1, state['pos'][2]]
                c.checked('material_job_park', park_target=point); c.park_target = point
        finally:
            if c.finish() is False:
                raise RuntimeError('Geology survey protected finish is unconfirmed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('automation', 'request', 'candidates', 'out'):
        p.add_argument('--'+name, required=True, type=Path)
    p.add_argument('--low-y', type=int, default=-64); p.add_argument('--high-y', type=int, default=96)
    p.add_argument('--biome', action='append', required=True)
    p.add_argument('--wait-stationary', action='store_true')
    a = p.parse_args(); rows = json.loads(a.candidates.read_text())
    request = json.loads(a.request.read_text())
    if not a.wait_stationary:
        run(a.automation, request, rows[0], a.low_y, a.high_y, a.out, set(a.biome)); return
    a.out.mkdir(exist_ok=False)
    attempt = 0
    while True:
        ready = wait_ready(a.automation, request, a.out/('waiting-%03d' % attempt))
        attempt += 1
        try:
            run(a.automation, request, rows[0], a.low_y, a.high_y,
                a.out/('attempt-%03d' % attempt), set(a.biome)); return
        except (RuntimeError,Handoff) as error:
            # This exact host rejection occurs before assigning a lease.
            # A new admission after a new stable window is a separate intent.
            current = read_fresh(a.automation)
            if not rejected_unowned_admission(a.automation, a.out/('attempt-%03d' % attempt), ready):
                raise
            write_json(a.out/('admission-refusal-%03d.json' % attempt),
                       {'detail':str(error), 'observed_at':current['time'],
                        'old_native_request_replayed':False, 'controller_acquired':False})


if __name__ == '__main__': main()
