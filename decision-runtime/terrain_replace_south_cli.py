"""Native, journaled south-lawn Y62 stone -> dirt repair; one cell by default.

Requires Kit's terrain_replace_protocol=1. This command never loads a world,
clears a safety lock, selects a different projection, or widens the ten-cell
allowlist. Its material lease keeps the player online under PvE guard after a
freshly verified high-air parking position is reached.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import Handoff, MaterialClient
import projection_dry_paving as paving
import projection_dry_paving_cli as paving_cli
from safety_interlock import require_unlocked
from terrain_replace_south import CELLS, PINNED, replace_batch


class TerrainClient(MaterialClient):
    def advise(self, goal, candidates, scene=None, fallback='wait'):
        return {'choice': 'wait' if 'wait' in candidates else fallback}


def validate_cells(raw, max_cells):
    if type(max_cells) is not int or not 1 <= max_cells <= len(CELLS):
        raise ValueError('This south-lawn phase permits only 1..10 exact cells')
    points = [paving._position(p) for p in (raw if raw is not None else CELLS[:max_cells])]
    if (len(points) != max_cells or len(set(points)) != len(points)
            or any(p not in PINNED for p in points)):
        raise ValueError('Each named cell must be unique and in the ten-cell lawn allowlist')
    return points


def preflight(root, points, park_high):
    require_unlocked(root)
    state = read_fresh(root)
    require_unlocked(root, state)
    selection = state.get('projection_selection') or {}
    key = selection.get('key')
    first = points[0]
    player = state.get('pos') or []
    if type(state.get('terrain_replace_protocol')) is not int or state['terrain_replace_protocol'] != 1:
        raise paving.PavingBlocked('Native terrain_replace_protocol=1 is not installed')
    if (not state.get('connected') or state.get('server', '').removesuffix(':25565') != paving.SITE['server']
            or state.get('dimension') != paving.SITE['dimension']
            or not isinstance(key, str) or not key
            or hashlib.sha256(key.encode()).hexdigest() != paving.SITE['placement_key_sha256']
            or tuple(selection.get('min') or ()) != paving.SITE['bounds']['min']
            or tuple(selection.get('max') or ()) != paving.SITE['bounds']['max']
            or state.get('screen') != '' or state.get('manual_movement')
            or state.get('health', 0) < 19 or state.get('food', 0) < 10
            or not state.get('flight') or not state.get('guard_armed')
            or not state.get('guard_pve_only') or state.get('guard_busy')
            or state.get('under_water') or (state.get('safety_hold') or {}).get('active')
            or (state.get('build_job') or {}).get('active')
            or (state.get('professional_printer') or {}).get('enabled')
            or any(state.get(flag) for flag in ('borer_active', 'chopping', 'navigating'))
            or not isinstance(player, list) or len(player) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in player)
            or math.hypot(player[0] - first[0] - .5, player[2] - first[2] - .5) > 31):
        raise paving.PavingBlocked('Current Kit, projection, player, or safety state is not ready for the south lawn')
    paving_cli.validate_park(park_high, state)
    return state


def _finish_receipt(client, root, out):
    """Confirm MaterialClient retained this lease's safe online high guard."""
    path = Path(out) / 'stock-safety.json'
    evidence = {'state': 'unconfirmed', 'evidence': str(path),
                'high_park_verified': False}
    try:
        receipt = json.loads(path.read_text(encoding='utf-8'))
        lease = getattr(getattr(client, 'heartbeat', None), 'id', None)
        park = getattr(client, 'park_target', None)
        snapshot = receipt.get('snapshot') or {}
        receipt_position = snapshot.get('pos')
        if (not isinstance(lease, str) or not 1 <= len(lease) <= 80
                or not all(ch.isalnum() or ch in '_-' for ch in lease)
                or not isinstance(park, list) or len(park) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in park)
                or receipt.get('action') != 'KEEP_PVE_GUARD'
                or receipt.get('lease') != lease
                or receipt.get('job_session') != client.task
                or snapshot.get('world_session') != client.world
                or not isinstance(receipt_position, list) or len(receipt_position) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in receipt_position)
                or abs(receipt_position[1] - park[1]) > 2
                or ((receipt_position[0] - park[0]) ** 2
                    + (receipt_position[2] - park[2]) ** 2
                    > MaterialClient.PARK_RADIUS_SQR)
                or snapshot.get('health', 0) < 18
                or snapshot.get('guard_armed') is not True
                or snapshot.get('guard_pve_only') is not True
                or snapshot.get('flight') is not True):
            return evidence
        current = read_fresh(root, wait_seconds=0)
        current_position = current.get('pos')
        current_lease = current.get('supervision_lease') or {}
        if (current.get('connected') is not True
                or current.get('world_session') != client.world
                or current.get('server', '').removesuffix(':25565') != paving.SITE['server']
                or current.get('dimension') != paving.SITE['dimension']
                or current.get('manual_movement')
                or current.get('screen') != ''
                or current.get('under_water')
                or current.get('health', 0) < 18
                or current.get('guard_armed') is not True
                or current.get('guard_pve_only') is not True
                or current.get('guard_busy')
                or current.get('flight') is not True
                or (current_lease and (current_lease.get('id') != lease
                    or current_lease.get('kind') != 'parking'))
                or not isinstance(current_position, list) or len(current_position) != 3
                or any(type(v) not in (int, float) or not math.isfinite(v)
                       for v in current_position)
                or abs(current_position[1] - park[1]) > 2
                or ((current_position[0] - park[0]) ** 2
                    + (current_position[2] - park[2]) ** 2
                    > MaterialClient.PARK_RADIUS_SQR)):
            return evidence
        return {'state': 'high_guard_confirmed', 'evidence': str(path),
                'confirmation': 'fresh_connected_high_pve_guard',
                'park_position': current_position, 'high_park_verified': True}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        return evidence


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Version-specific Kit automation directory')
    parser.add_argument('--out', type=Path, required=True, help='New directory for this bounded run')
    parser.add_argument('--max-cells', type=int, default=1)
    parser.add_argument('--cell', nargs=3, type=int, action='append', metavar=('X', 'Y', 'Z'))
    parser.add_argument('--reconcile-pre-send-evidence', type=Path,
                        help='Immutable JSON proof for one explicit prior pre-send rejection')
    parser.add_argument('--reconcile-post-send-evidence', type=Path,
                        help='Immutable proof that one explicit waiting lift produced and recovered its grass drop')
    parser.add_argument('--park-high', nargs=3, type=float, required=True,
                        metavar=('X', 'Y', 'Z'))
    args = parser.parse_args(argv)
    client = None
    result = {'status': 'blocked_before_run', 'done': 0, 'reason': 'Run did not start'}
    try:
        if (args.reconcile_pre_send_evidence is not None
                and args.reconcile_post_send_evidence is not None):
            raise ValueError('Choose only one terrain reconciliation evidence flag')
        if (args.reconcile_pre_send_evidence is not None
                and (args.max_cells != 1 or args.cell is None or len(args.cell) != 1)):
            raise ValueError('Pre-send reconciliation requires one explicit --cell and --max-cells 1')
        if (args.reconcile_post_send_evidence is not None
                and (args.max_cells != 1 or args.cell is None or len(args.cell) != 1)):
            raise ValueError('Post-send reconciliation requires one explicit --cell and --max-cells 1')
        points = validate_cells(args.cell, args.max_cells)
        if args.out.exists() and any(args.out.iterdir()):
            raise ValueError('Output directory must be new or empty')
        pre_send_evidence = None
        if args.reconcile_pre_send_evidence is not None:
            pre_send_evidence = json.loads(
                args.reconcile_pre_send_evidence.read_text(encoding='utf-8'))
            if not isinstance(pre_send_evidence, dict):
                raise ValueError('Pre-send reconciliation evidence must be a JSON object')
        post_send_evidence = None
        if args.reconcile_post_send_evidence is not None:
            post_send_evidence = json.loads(
                args.reconcile_post_send_evidence.read_text(encoding='utf-8'))
            if not isinstance(post_send_evidence, dict):
                raise ValueError('Post-send reconciliation evidence must be a JSON object')
        preflight(args.root, points, args.park_high)
        client = TerrainClient(args.root, args.out, server=paving.SITE['server'],
                               record_experience=False, remote_finish='guard',
                               park_target=args.park_high)
        args.out.mkdir(parents=True, exist_ok=True)
        paving_cli.verify_high_park(client, args.park_high)
        result = {'schema': 1, 'status': 'running', 'world_session': client.world,
                  'task_session': client.task, 'started_at': time.time(),
                  'cells_requested': [list(p) for p in points], 'done': 0,
                  'receipts': [], 'reason': None}
        write_json(args.out / 'progress.json', result)
        # A partial batch is never hidden: the stable per-cell journal remains
        # authoritative even if this progress file cannot be updated.
        for pos in points:
            batch_args = {'cells': [pos], 'max_cells': 1}
            if args.reconcile_pre_send_evidence is not None:
                batch_args['pre_send_evidence'] = pre_send_evidence
            if args.reconcile_post_send_evidence is not None:
                batch_args['post_send_evidence'] = post_send_evidence
            receipt = replace_batch(client, **batch_args)
            if len(receipt) != 1 or receipt[0].get('result') != 'placed':
                raise paving.PavingPending('One exact cell lacked a confirmed completion receipt')
            result['receipts'].append(receipt[0])
            result['done'] += 1
            write_json(args.out / 'progress.json', result)
        result['status'] = 'completed'
    except paving.PavingPending as error:
        result.update(status='pending_review', reason=str(error))
    except Handoff as error:
        result.update(status='manual_handoff', reason=str(error))
    except (paving.PavingBlocked, RuntimeError, ValueError, OSError,
            KeyError, TypeError, AttributeError, AssertionError) as error:
        result.update(status='blocked', reason=str(error))
    finally:
        if client is not None:
            try:
                client.finish()
            except (Handoff, RuntimeError, ValueError, OSError,
                    KeyError, TypeError, AttributeError) as error:
                result['finish_error'] = str(error)
            result['finish'] = _finish_receipt(client, args.root, args.out)
            if (result['status'] == 'completed'
                    and result['finish']['state'] != 'high_guard_confirmed'):
                result['work_status'], result['status'] = 'completed', 'finish_unconfirmed'
        result['ended_at'] = time.time()
        if args.out.exists() and (args.out / 'progress.json').exists():
            write_json(args.out / 'progress.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if (result['status'] == 'completed' and 'finish_error' not in result
                 and result.get('finish', {}).get('state') == 'high_guard_confirmed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
