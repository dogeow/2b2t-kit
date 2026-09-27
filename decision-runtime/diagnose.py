"""Compact offline diagnosis from local snapshots and a bounded log tail. No game/network actions."""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from kit_runtime.diagnostics import redact, tail_events

ROOT = Path('/Applications/.minecraft/versions/26.1.2/config/twob2tkit/automation')


def read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def fault_kind(detail: str) -> str:
    value = detail.lower()
    for kind, words in (
        ('authorization_or_safety', ('offline kit', 'safety lock', 'health', '血量', '安全锁')),
        ('state_or_connection', ('stale', 'disconnect', 'not alive', '离开世界', 'connection', '连接')),
        ('navigation', ('route', 'collision', 'unsafe drop', 'occluded', 'out of reach', '通道', '碰撞')),
        ('server_confirmation', ('acknowledge', 'not confirmed', '未确认', '服务器未')),
        ('supplies', ('missing', 'insufficient', 'space', '缺料', '背包')),
    ):
        if any(word in value for word in words):
            return kind
    return 'other'


def summarize_run(directory: Path) -> dict:
    events = tail_events(directory / 'events.jsonl')
    timings: dict[str, list[float]] = defaultdict(list)
    failures = []
    for event in events:
        duration = event.get('duration_ms')
        if isinstance(duration, (float, int)) and math.isfinite(duration) and duration >= 0:
            timings[str(event.get('op', 'unknown'))].append(duration)
        if event.get('phase') in ('waiting', 'error', 'stopped'):
            detail = str(event.get('detail', ''))
            failures.append({'time': event.get('time'), 'op': event.get('op'),
                             'kind': fault_kind(detail), 'detail': detail[:240],
                             'request_id': event.get('request_id')})
    expensive = []
    for operation, values in timings.items():
        values.sort()
        expensive.append({'op': operation, 'observed_calls': len(values),
                          'total_ms': round(sum(values)),
                          'p95_ms': round(values[max(0, math.ceil(len(values) * .95) - 1)])})
    decisions = [event for event in tail_events(directory / 'jev-decisions.jsonl') if event.get('kind') == 'decision']
    return redact({'directory': str(directory), 'scope': 'bounded_last_200_events_not_full_history',
                   'events_observed': len(events), 'last_event_at': events[-1].get('time') if events else None,
                   'slow_operations': sorted(expensive, key=lambda row: -row['total_ms'])[:5],
                   'failure_counts': dict(Counter(row['kind'] for row in failures)),
                   'recent_failures': failures[-5:],
                   'jev': {'observed_decisions': len(decisions),
                           'sources': dict(Counter(row.get('source', 'unknown') for row in decisions)),
                           'fallbacks': dict(Counter(row.get('reason') for row in decisions if row.get('reason')))}})


def diagnose(root: Path, run: Path | None = None) -> dict:
    state = read_object(root / 'status.json')
    hold = read_object(root / 'assistant-control-hold.json')
    current = {'available': bool(state), 'connected': state.get('connected'),
               'snapshot_age_seconds': round((time.time() * 1000 - state['time']) / 1000, 1) if isinstance(state.get('time'), (int, float)) else None,
               'observed_host': state.get('kit_version'), 'observed_engine': state.get('runtime_version'),
               'screen': state.get('screen'), 'op': state.get('op'), 'phase': state.get('phase'),
               'detail': state.get('detail'), 'health': state.get('health'),
               'manual_control': state.get('manual_movement'),
               'assistant_offline_only': hold.get('active', False),
               'native_health_lock': read_object(root / 'safety-hold.json').get('active', False)}
    result = {'game': current, 'performed_game_or_network_actions': False}
    if run is not None:
        result['run'] = summarize_run(run)
    return redact(result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--automation', type=Path, default=ROOT)
    parser.add_argument('--run', type=Path)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.automation, args.run), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
