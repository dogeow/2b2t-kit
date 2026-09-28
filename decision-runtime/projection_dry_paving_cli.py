"""Bounded, deterministic launcher for the pinned full-yard dry paving cells.

The CLI is intentionally separate from material jobs and never asks an AI to
choose or approve a block. Each batch comes from a fresh complete projection
audit; ``projection_dry_paving.pave_batch`` remains the sole mutating path.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import time

from kit_runtime.journal import write_json
from fast_descent import descend_if_clear
from live_snapshot import read_fresh
from material_client import Handoff, MaterialClient, high_park_clearance
import projection_dry_paving as paving
from safety_interlock import require_unlocked


PENDING_PHASES = frozenset({'mine_intent', 'mined', 'pickup_intent', 'place_intent'})
LOCAL_GEOMETRY_BLOCKERS = frozenset({
    'Natural target changed or has unsafe block properties',
    'Dry natural support below the paving cell is unverified',
    'Paving body column is occupied',
    'Fluid or block entity lies in the neighbor scan',
    'Nearby non-solid feature may depend on this surface',
})


class DeterministicPavingClient(MaterialClient):
    """Keep guarded health recovery local, without a Jev recommendation."""

    def advise(self, goal, candidates, scene=None, fallback='wait'):
        return {'choice': 'wait' if 'wait' in candidates else fallback}


def validate_limits(minutes, max_cells, batch_size):
    if type(minutes) is not int or not 1 <= minutes <= 60:
        raise ValueError('Minutes must be an integer from 1 through 60')
    if type(max_cells) is not int or not 1 <= max_cells <= len(paving.SITE['pinned_conflicts']):
        raise ValueError('Max cells must be an integer from 1 through 79')
    if type(batch_size) is not int or not 1 <= batch_size <= 4:
        raise ValueError('Batch size must be an integer from 1 through 4')


def validate_cells(cells, max_cells):
    if cells is None:
        if max_cells == 1:
            raise ValueError('A one-cell validation run requires an explicit --cell X Y Z')
        return None
    points = [paving._position(pos) for pos in cells]
    if (not points or len(points) < max_cells
            or max_cells == 1 and len(points) != 1
            or len(set(points)) != len(points)
            or any(pos not in paving.SITE['pinned_conflicts']
                   or paving._protected(pos, paving.SITE) for pos in points)):
        raise ValueError('Explicit cells must be unique unprotected members of the pinned 79-cell list')
    return frozenset(points)


def validate_park(park_high, state):
    """Force MaterialClient to verify the high park column before owning work."""
    if (not isinstance(park_high, (list, tuple)) or len(park_high) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in park_high)):
        raise ValueError('High park must contain three finite coordinates')
    low, high = paving.SITE['bounds']['min'], paving.SITE['bounds']['max']
    x, y, z = park_high
    if not (low[0] <= x <= high[0] + 1 and low[2] <= z <= high[2] + 1
            and high[1] + 25 <= y <= 320):
        raise ValueError('High park must be above the pinned courtyard by at least 25 blocks')
    pos = state.get('pos')
    if (not isinstance(pos, list) or len(pos) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in pos)
            or math.hypot(pos[0] - x, pos[2] - z) > 32):
        raise ValueError('Start within 32 horizontal blocks of the high park for column verification')


def preflight(root, park_high):
    """Reject a wrong host, site, or manual takeover before acquiring a lease."""
    require_unlocked(root)
    state = read_fresh(root)
    require_unlocked(root, state)
    site = paving.SITE
    selection = state.get('projection_selection') or {}
    key = selection.get('key')
    if (not state.get('connected') or state.get('server', '').removesuffix(':25565') != site['server']
            or state.get('dimension') != site['dimension'] or state.get('manual_movement')
            or state.get('screen') != '' or state.get('dry_paving_protocol') != 1
            or type(state.get('dry_paving_protocol')) is not int
            or tuple(selection.get('min') or ()) != site['bounds']['min']
            or tuple(selection.get('max') or ()) != site['bounds']['max']
            or not isinstance(key, str)
            or hashlib.sha256(key.encode()).hexdigest() != site['placement_key_sha256']
            or state.get('health', 0) < 19 or state.get('food', 0) < 10
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('guard_busy') or not state.get('flight') or state.get('under_water')
            or state.get('air_return_active') or (state.get('safety_hold') or {}).get('active')
            or (state.get('build_job') or {}).get('active')
            or (state.get('professional_printer') or {}).get('enabled')
            or any(state.get(flag) for flag in ('borer_active', 'chopping', 'navigating'))):
        raise paving.PavingBlocked('Current Kit protocol, courtyard, control, or safety state is not ready')
    validate_park(park_high, state)
    return state


def verify_high_park(client, park_high):
    """Recheck the actor and the actual park column after lease acquisition."""
    validate_park(park_high, client.status())
    x, y, z = map(math.floor, park_high)
    reply = client.request('scan', min=[x, -64, z], max=[x, 320, z], details=True)
    if (reply.get('phase') not in (None, 'done') or reply.get('world_session') != client.world
            or not isinstance(reply.get('blocks'), list)):
        raise paving.PavingBlocked('High park column scan is incomplete')
    seen = set()
    for row in reply['blocks']:
        pos = paving._position(row.get('pos'))
        if pos in seen or pos[0] != x or pos[2] != z or not -64 <= pos[1] <= 320:
            raise paving.PavingBlocked('High park column scan has unexpected cells')
        seen.add(pos)
        if y - 2 <= pos[1] <= y + 2:
            raise paving.PavingBlocked('High park target space is occupied')
    clearance = high_park_clearance(reply['blocks'], park_high[1])
    if clearance < 20:
        raise paving.PavingBlocked('High park has less than 20 blocks of verified ground clearance')
    return {'park_target': list(park_high), 'world_session': client.world,
            'ground_clearance': clearance}


def _audit_receipt(state, model, audit):
    return {'world_session': state['world_session'],
            'placement_key_sha256': paving.SITE['placement_key_sha256'],
            'model_hash': model['content_hash'], 'model_observed_at': model['observed_at'],
            'audit_observed_at': audit['observed_at'], 'matched': audit['matched'],
            'total': audit['total'], 'mismatch_count': len(audit['mismatches'])}


def _journal_record(client, pos, state, model):
    path = paving._journal_path(client, paving.SITE, pos)
    record = paving._load_journal(path, paving.SITE, pos,
                                  state['projection_selection']['key'], model['content_hash'])
    return path, record


def _free_drop_slots(state):
    """Count distinct, explicitly empty backpack slots before any travel.

    The native inventory snapshot does not report arbitrary item components.
    A partial stack of the right item ID therefore cannot prove that the
    original block's drop will merge into it.
    """
    rows = state.get('inventory')
    if not isinstance(rows, list):
        raise paving.PavingBlocked('Backpack capacity observation is unavailable')
    slots = {}
    for row in rows:
        if not isinstance(row, dict):
            raise paving.PavingBlocked('Backpack capacity observation is malformed')
        slot = row.get('slot')
        if type(slot) is not int or not 0 <= slot < 36:
            continue
        if slot in slots:
            raise paving.PavingBlocked('Backpack capacity observation has duplicate slots')
        slots[slot] = row
    return sum(row.get('item') == 'minecraft:air' and row.get('count') == 0
               for row in slots.values())


def select_batch(client, limit, allowed_cells=None):
    """Name stocked audited cells; reject old intents before considering supplies."""
    if type(limit) is not int or not 1 <= limit <= 4:
        raise ValueError('One batch names one to four cells')
    state, model, audit = paving._fresh_context(client, paving.SITE)
    receipt = _audit_receipt(state, model, audit)
    candidates = []
    for pos in paving.SITE['pinned_conflicts']:
        # Unresolved native intents anywhere in the pinned yard block new
        # work, even when this run explicitly names a different cell.
        _, record = _journal_record(client, pos, state, model)
        if record is not None and record['phase'] in PENDING_PHASES:
            raise paving.PavingPending('Uncertain prior intent at %s; inspect the cell journal' % (pos,))
        if record is not None and record['phase'] == 'complete':
            if any(row.get('pos') == list(pos) for row in audit['mismatches']):
                raise paving.PavingPending('Previously completed cell changed at %s' % (pos,))
            continue
        if allowed_cells is not None and pos not in allowed_cells:
            continue
        if paving._protected(pos, paving.SITE):
            continue
        recovered = record is not None and record['phase'] == 'recovered'
        try:
            row = paving._target(model, audit, pos, paving.SITE, air=recovered)
        except paving.PavingBlocked:
            if record is not None:
                raise paving.PavingPending('Recovered cell changed at %s' % (pos,))
            continue
        candidates.append((pos, paving._block(row['expected']), recovered, row['actual']))
    player = state['pos']
    candidates.sort(key=lambda entry: (not entry[2],
                                       (entry[0][0] + .5 - player[0]) ** 2
                                       + (entry[0][2] + .5 - player[2]) ** 2,
                                       entry[0][2], entry[0][0]))
    available = paving._counts(state)
    free_drop_slots = _free_drop_slots(state)
    missing = Counter()
    geometry_skips = []
    capacity_skips = 0
    selected = []
    for pos, item, recovered, actual in candidates:
        if available[item] < 1:
            if recovered:
                raise paving.PavingPending('Recovered cell at %s awaits its replacement item' % (pos,))
            missing[item] += 1
            continue
        if len(selected) < limit:
            if not recovered:
                # Reserve one provably empty slot per potential mined drop.
                # Do not rely on replacement placement freeing a slot, or on
                # a partial stack merging with an unknown-component drop.
                if free_drop_slots <= 0:
                    capacity_skips += 1
                    continue
                # This is a read-only 3x4x3 scan of the exact audited cell.
                # A local obstruction excludes this untouched candidate;
                # scan/world-scope failures still stop the entire run.
                cells = paving._scan(client, pos)
                try:
                    paving._geometry(cells, pos, actual)
                except paving.PavingBlocked as error:
                    if str(error) not in LOCAL_GEOMETRY_BLOCKERS:
                        raise
                    geometry_skips.append({'pos': list(pos), 'reason': str(error)})
                    continue
            selected.append(list(pos))
            available[item] -= 1
            if not recovered:
                free_drop_slots -= 1
    receipt['selection'] = {'audited_candidates': len(candidates),
                            'missing_replacement_cells': dict(sorted(missing.items())),
                            'geometry_skips': geometry_skips,
                            'capacity_skips': capacity_skips,
                            'free_drop_slots_after_reservation': free_drop_slots}
    return selected, receipt


def _cell_receipt(client, pos, state, model, audit):
    path, record = _journal_record(client, tuple(pos), state, model)
    if record is None or record['phase'] != 'complete':
        raise paving.PavingPending('No complete cell journal at %s' % (tuple(pos),))
    if any(row.get('pos') == pos for row in audit['mismatches']):
        raise paving.PavingPending('Full audit still disagrees at %s' % (tuple(pos),))
    return {'pos': pos, 'expected': record['expected'], 'original': record['actual'],
            'journal': str(path), 'journal_phase': record['phase'],
            'journal_updated_at_ns': record['updated_at_ns'],
            'audit': _audit_receipt(state, model, audit)}


def _write_progress(out, progress):
    write_json(Path(out) / 'progress.json', progress)


def _append_event(out, event):
    path = Path(out) / 'events.jsonl'
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def _first_trip_descent(client, cells, before, initial_state, verified_high_park):
    """Try one ordinary guarded descent, only from this run's verified high start.

    A recovered cell has already had a block removed, so it uses the original
    cautious approach. ``pave_batch`` still performs its own fresh audit and
    native placement checks after this travel-only optimization.
    """
    park = (verified_high_park or {}).get('park_target')
    if (not isinstance(park, list) or len(park) != 3
            or (verified_high_park or {}).get('world_session') != client.world
            or (verified_high_park or {}).get('ground_clearance', 0) < 20
            or not isinstance(initial_state, dict)
            or initial_state.get('world_session') != client.world):
        return {'used': False, 'reason': 'This run has no verified high-start receipt'}
    state = client.status()
    key = paving._safe_state(client, state, paving.SITE)
    if (before.get('world_session') != client.world
            or before.get('placement_key_sha256') != paving.SITE['placement_key_sha256']
            or hashlib.sha256(key.encode()).hexdigest() != before['placement_key_sha256']):
        raise paving.PavingBlocked('Projection selection changed before fast descent')
    validate_park(park, state)
    start = initial_state.get('pos')
    current = state.get('pos')
    if (not isinstance(start, list) or len(start) != 3
            or not isinstance(current, list) or len(current) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in (*start, *current, *park))
            or abs(start[1] - park[1]) > 3
            or abs(current[1] - park[1]) > 3
            or math.dist(start, current) > 4):
        return {'used': False, 'reason': 'Actor did not remain at the original high start'}
    model = {'content_hash': before.get('model_hash')}
    for pos in paving.SITE['pinned_conflicts']:
        _, record = _journal_record(client, pos, state, model)
        if record is not None and record['phase'] in PENDING_PHASES:
            raise paving.PavingPending('Uncertain prior intent at %s; inspect the cell journal' % (pos,))
    for pos in cells:
        _, record = _journal_record(client, tuple(pos), state, model)
        if record is not None:
            if record['phase'] == 'recovered':
                return {'used': False, 'reason': 'Recovered cell requires cautious approach'}
            raise paving.PavingPending('Selected cell already has a journal at %s' % (tuple(pos),))
    result = descend_if_clear(client, target_y=63, braking_margin=16)
    if not isinstance(result, dict) or type(result.get('used')) is not bool:
        raise paving.PavingBlocked('Fast descent returned an unverified receipt')
    # Even a native used:false response must leave the actor under the same
    # leased safety guard before the regular paving path may continue.
    paving._safe_state(client, client.status(), paving.SITE)
    return result


def _finish_receipt(client, out):
    out = Path(out)
    for name in ('stock-safety.json', 'park-fallback.json', 'finish-drain.json'):
        path = out / name
        if path.exists():
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                record = {'unreadable': True}
            if name == 'stock-safety.json' and record.get('action') == 'KEEP_PVE_GUARD':
                return {'state': 'high_guard_confirmed', 'evidence': str(path)}
            if name == 'park-fallback.json':
                return {'state': 'safe_logout_requested', 'evidence': str(path),
                        'reason': record.get('reason')}
    return {'state': 'unconfirmed', 'evidence': str(out / 'finish-drain.json')}


def run(client, out, *, minutes=20, max_cells, batch_size=4, allowed_cells=None,
        fast_first_descent=False, initial_state=None, verified_high_park=None,
        monotonic=time.monotonic, wall_time=time.time, pave=paving.pave_batch):
    """Run a bounded session, writing durable progress before every batch."""
    validate_limits(minutes, max_cells, batch_size)
    allowed_cells = validate_cells(allowed_cells, max_cells)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    progress_path = out / 'progress.json'
    if progress_path.exists():
        raise ValueError('Output already contains a paving progress record; choose a new run directory')
    started = monotonic()
    progress = {'schema': 1, 'site': paving.SITE['name'],
                'placement_key_sha256': paving.SITE['placement_key_sha256'],
                'world_session': client.world, 'task_session': client.task,
                'started_at': wall_time(), 'minutes': minutes, 'max_cells': max_cells,
                'batch_size': batch_size,
                'allowed_cells': [list(pos) for pos in sorted(allowed_cells)] if allowed_cells else None,
                'status': 'running', 'done': 0,
                'batches': [], 'cells': [], 'reason': None}
    _write_progress(out, progress)
    first_trip_checked = False
    try:
        while progress['done'] < max_cells:
            if monotonic() - started >= minutes * 60:
                progress['status'] = 'time_limit'
                break
            limit = min(batch_size, max_cells - progress['done'])
            # Short validation runs get one complete cell before the deadline
            # is checked again; a native in-flight action is never interrupted.
            if minutes * 60 - (monotonic() - started) < 300:
                limit = 1
            cells, before = select_batch(client, limit, allowed_cells)
            progress['last_audit'] = before
            if not cells:
                selection = before['selection']
                missing = selection['missing_replacement_cells']
                geometry_skips = selection['geometry_skips']
                capacity_skips = selection['capacity_skips']
                if capacity_skips:
                    progress['status'] = 'inventory_full'
                    progress['reason'] = ('No verified empty backpack slot for a mined paving drop; '
                                          '%d audited candidates withheld before travel'
                                          % capacity_skips)
                elif missing and not geometry_skips:
                    progress['status'] = 'materials_exhausted'
                    progress['reason'] = 'No held replacement blocks for audited paving cells: ' \
                        + ', '.join('%s=%d' % (item, count) for item, count in missing.items())
                else:
                    progress['status'] = 'no_eligible_cells'
                    if geometry_skips:
                        progress['reason'] = '%d audited paving cells failed local dry geometry preflight' \
                            % len(geometry_skips)
                break
            if fast_first_descent and not first_trip_checked:
                first_trip_checked = True
                transit = {'status': 'attempting', 'selected': cells,
                           'started_at': wall_time()}
                progress['first_trip_transit'] = transit
                _write_progress(out, progress)
                _append_event(out, {'event': 'first_trip_transit_started', **transit})
                try:
                    descent = _first_trip_descent(client, cells, before,
                                                  initial_state, verified_high_park)
                except (Handoff, paving.PavingBlocked, paving.PavingPending, RuntimeError,
                        OSError, ValueError, KeyError, TypeError, AttributeError,
                        AssertionError) as error:
                    transit.update(status='blocked', used=False, reason=str(error),
                                   finished_at=wall_time())
                    _write_progress(out, progress)
                    _append_event(out, {'event': 'first_trip_transit_finished', **transit})
                    raise
                transit.update(status='completed', **descent, finished_at=wall_time())
                _write_progress(out, progress)
                _append_event(out, {'event': 'first_trip_transit_finished', **transit})
            batch = {'positions': cells, 'before_audit': before,
                     'started_at': wall_time(), 'status': 'in_progress',
                     'cell_receipts': []}
            progress['batches'].append(batch)
            _write_progress(out, progress)
            _append_event(out, {'event': 'batch_started', **batch})

            def cell_complete(result):
                index = len(batch['cell_receipts'])
                if (index >= len(cells) or result.get('pos') != cells[index]
                        or result.get('result') != 'placed'):
                    raise paving.PavingPending('Batch returned an unexpected cell receipt')
                state, model, audit = paving._fresh_context(client, paving.SITE)
                receipt = _cell_receipt(client, cells[index], state, model, audit)
                batch['cell_receipts'].append(receipt)
                progress['cells'].append(receipt)
                progress['done'] += 1
                progress['last_audit'] = receipt['audit']
                _write_progress(out, progress)
                _append_event(out, {'event': 'cell_audited', **receipt})

            results = pave(client, cells, on_cell_complete=cell_complete)
            if (not isinstance(results, list) or len(results) != len(cells)
                    or len(batch['cell_receipts']) != len(cells)
                    or any(row.get('pos') != cells[index] or row.get('result') != 'placed'
                           for index, row in enumerate(results))):
                raise paving.PavingPending('Batch returned an incomplete or unexpected cell receipt')
            state, model, audit = paving._fresh_context(client, paving.SITE)
            receipts = [_cell_receipt(client, pos, state, model, audit) for pos in cells]
            batch.update(status='audited', after_audit=_audit_receipt(state, model, audit),
                         finished_at=wall_time(), cell_receipts=receipts)
            _write_progress(out, progress)
            _append_event(out, {'event': 'batch_audited', **batch})
        if progress['done'] >= max_cells:
            progress['status'] = 'completed'
    except paving.PavingPending as error:
        progress['status'], progress['reason'] = 'pending_review', str(error)
    except Handoff as error:
        progress['status'], progress['reason'] = 'manual_handoff', str(error)
    except (paving.PavingBlocked, RuntimeError, OSError, ValueError,
            KeyError, TypeError, AttributeError, AssertionError) as error:
        progress['status'], progress['reason'] = 'blocked', str(error)
    except BaseException as error:
        progress['status'], progress['reason'] = 'interrupted', repr(error)
        raise
    finally:
        progress['ended_at'] = wall_time()
        if progress['batches'] and progress['batches'][-1]['status'] == 'in_progress':
            batch = progress['batches'][-1]
            batch['status'] = 'stopped_before_batch_receipt'
            batch['journal_phases'] = {}
            for pos in batch['positions']:
                path = paving._journal_path(client, paving.SITE, tuple(pos))
                try:
                    record = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
                    batch['journal_phases']['_'.join(map(str, pos))] = record.get('phase') if record else None
                except (OSError, ValueError, AttributeError):
                    batch['journal_phases']['_'.join(map(str, pos))] = 'unreadable'
            if progress['status'] not in ('manual_handoff', 'interrupted') \
                    and any(phase in PENDING_PHASES or phase == 'unreadable'
                            for phase in batch['journal_phases'].values()):
                progress['status'] = 'pending_review'
        _write_progress(out, progress)
        _append_event(out, {'event': 'run_stopped', 'status': progress['status'],
                            'reason': progress['reason'], 'done': progress['done']})
    return progress


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Kit automation directory')
    parser.add_argument('--out', type=Path, required=True, help='New run evidence directory')
    parser.add_argument('--park-high', nargs=3, type=float, required=True,
                        metavar=('X', 'Y', 'Z'), help='Verified high PvE guard park')
    parser.add_argument('--minutes', type=int, default=20)
    parser.add_argument('--max-cells', type=int, required=True)
    parser.add_argument('--cell', nargs=3, type=int, action='append',
                        metavar=('X', 'Y', 'Z'), help='Exact pinned cell; required for one-cell runs')
    parser.add_argument('--batch-size', type=int, default=4)
    parser.add_argument('--fast-first-descent', action='store_true',
                        help='Opt in to one guarded clear-column descent on a new first batch')
    args = parser.parse_args(argv)
    client = None
    park_verified = False
    run_started = False
    result = {'status': 'blocked_before_run', 'reason': 'Run did not start', 'done': 0}
    try:
        validate_limits(args.minutes, args.max_cells, args.batch_size)
        allowed_cells = validate_cells(args.cell, args.max_cells)
        if args.out.exists() and any(args.out.iterdir()):
            raise ValueError('Output directory must be new or empty for unambiguous receipts')
        initial = preflight(args.root, args.park_high)
        client = DeterministicPavingClient(args.root, args.out, server=paving.SITE['server'],
                                           record_experience=False, remote_finish='guard',
                                           park_target=args.park_high)
        park = verify_high_park(client, args.park_high)
        park_verified = True
        run_started = True
        result = run(client, args.out, minutes=args.minutes, max_cells=args.max_cells,
                     batch_size=args.batch_size, allowed_cells=allowed_cells,
                     fast_first_descent=args.fast_first_descent, initial_state=initial,
                     verified_high_park=park)
        result['verified_high_park'] = park
    except (Handoff, paving.PavingBlocked, RuntimeError, OSError,
            ValueError, KeyError, TypeError, AttributeError,
            AssertionError, KeyboardInterrupt) as error:
        result = {'status': 'blocked_before_run', 'reason': str(error), 'done': 0}
        if isinstance(error, AssertionError) and not result['reason']:
            result['reason'] = 'Material client initial-state assertion failed'
        if run_started:
            try:
                saved = json.loads((args.out / 'progress.json').read_text(encoding='utf-8'))
                if saved.get('schema') == 1 and type(saved.get('done')) is int:
                    result = {**saved, 'reason': result['reason'],
                              'status': 'interrupted' if isinstance(error, KeyboardInterrupt)
                              else 'blocked'}
            except (OSError, ValueError, AttributeError):
                pass
    finally:
        if client is not None:
            if not park_verified:
                try:
                    client.request('safe_logout')
                except (Handoff, RuntimeError, OSError, ValueError,
                        KeyError, TypeError, AttributeError, AssertionError):
                    pass
            try:
                client.finish()
            except (Handoff, RuntimeError, OSError, ValueError,
                    KeyError, TypeError, AttributeError, AssertionError) as error:
                result['finish_error'] = str(error)
            if (args.out / 'progress.json').exists():
                result['finish'] = _finish_receipt(client, args.out)
                if (result['status'] in ('completed', 'time_limit', 'no_eligible_cells',
                                         'materials_exhausted')
                        and result['finish']['state'] != 'high_guard_confirmed'):
                    result['work_status'], result['status'] = result['status'], 'finish_unconfirmed'
                result['terminal'] = True
                _write_progress(args.out, result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result['status'] in ('completed', 'time_limit', 'no_eligible_cells',
                                     'materials_exhausted') \
        and result.get('finish', {}).get('state') == 'high_guard_confirmed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
