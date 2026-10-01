"""Scanned y74 approach, one horse nudge, and verified high-guard finish."""
import argparse
import json
from pathlib import Path

from construction_obstruction import (HorseNudgeWaiting, approach_and_nudge_explicit_horse,
                                      write_result)
from material_client import MaterialClient


class GuardFinishUnconfirmed(RuntimeError):
    def __init__(self, result):
        super().__init__('High guarded parking was not confirmed after horse handling')
        self.result = result


class HorseApproachFailed(RuntimeError):
    def __init__(self, result):
        super().__init__(result.get('detail', 'Horse approach stopped before a nudge'))
        self.result = result


def verify_high_guard_finish(client):
    receipt_path = Path(client.out) / 'stock-safety.json'
    try:
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        state = client.raw()
    except (OSError, ValueError, RuntimeError) as error:
        raise GuardFinishUnconfirmed({'high_guard_finish': {'confirmed': False,
                                     'reason': str(error)}}) from error
    heartbeat = getattr(getattr(client, 'heartbeat', None), 'id', None)
    snapshot = receipt.get('snapshot') or {}
    confirmed = (receipt.get('action') == 'KEEP_PVE_GUARD'
                 and receipt.get('lease') == heartbeat
                 and receipt.get('job_session') == getattr(client, 'task', None)
                 and snapshot.get('world_session') == getattr(client, 'world', None)
                 and state.get('world_session') == getattr(client, 'world', None)
                 and state.get('connected') and state.get('guard_armed')
                 and state.get('guard_pve_only') and state.get('flight')
                 and state.get('health', 0) >= 18 and client.park_near(state))
    evidence = {'confirmed': bool(confirmed), 'action': receipt.get('action'),
                'lease': receipt.get('lease'), 'pos': state.get('pos'),
                'health': state.get('health'), 'flight': state.get('flight'),
                'guard_armed': state.get('guard_armed')}
    if not confirmed:
        raise GuardFinishUnconfirmed({'high_guard_finish': evidence})
    return evidence


def execute(client, cell, expected_state, scout_y, wait_for_horse_seconds):
    code = 0;approach_failure = None;finish_failure = None
    try:
        result = approach_and_nudge_explicit_horse(
            client, cell, expected_state, scout_y=scout_y,
            wait_for_horse_seconds=wait_for_horse_seconds)
    except HorseNudgeWaiting as waiting:
        result = waiting.reply;code = 2
    except Exception as failure:
        approach_failure = failure
        result = {'phase': 'blocked', 'detail': str(failure)}
    finally:
        try:client.finish()
        except Exception as failure:finish_failure = failure
    try:finish = verify_high_guard_finish(client)
    except GuardFinishUnconfirmed as failure:
        result = result if isinstance(result, dict) else {}
        result['high_guard_finish'] = failure.result['high_guard_finish']
        raise GuardFinishUnconfirmed(result) from failure
    result = dict(result);result['high_guard_finish'] = finish
    if finish_failure is not None and approach_failure is None:
        approach_failure = finish_failure;result['phase'] = 'blocked'
        result['detail'] = 'High guard finish raised after horse handling: ' + str(finish_failure)
    if approach_failure is not None:
        raise HorseApproachFailed(result) from approach_failure
    return result, code


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cell', type=float, nargs=3, required=True, metavar=('X', 'Y', 'Z'))
    parser.add_argument('--scout-y', type=float, default=74.0)
    parser.add_argument('--wait-for-horse-seconds', type=float, default=30.0)
    parser.add_argument('--expected-state', required=True)
    parser.add_argument('--park-high', type=float, nargs=3, required=True, metavar=('X', 'Y', 'Z'))
    parser.add_argument('--server', default='simpcraft.com:25565')
    args = parser.parse_args(argv)
    client = MaterialClient(args.root, args.out, server=args.server,
                            remote_finish='guard', park_target=args.park_high)
    try:
        result, code = execute(client, args.cell, args.expected_state, args.scout_y,
                               args.wait_for_horse_seconds)
    except GuardFinishUnconfirmed as failure:
        result = failure.result;code = 3
    except HorseApproachFailed as failure:
        result = failure.result;code = 4
    write_result(args.out / 'horse-nudge-result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
