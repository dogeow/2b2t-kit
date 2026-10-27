"""Observe planner latency without changing action ownership or outcome fences."""
from collections import Counter
import json
import math
import time
from pathlib import Path
from kit_runtime.journal import write_json


def summarize(rows):
    durations = Counter()
    counts = Counter()
    gaps = 0.0
    for row in rows:
        counts[row['op']] += 1
        durations[row['op']] += row['elapsed_seconds']
        gaps += row.get('planner_gap_seconds', 0)
    warnings = []
    if counts['projection_audit'] > max(4, counts['professional_print'] * 2):
        warnings.append('Repeated full projection audits dominate small print batches')
    if rows and gaps > sum(durations.values()) * .25:
        warnings.append('Time without a queued action exceeds 25% of action time')
    masks = [r['mask_size'] for r in rows if r.get('mask_size')]
    if len(masks) >= 3 and sum(masks) / len(masks) <= 5:
        warnings.append('Printing uses at most five cells per batch on average; check reach-safe grouping')
    cells = sum(r.get('confirmed_print_cells', 0) for r in rows)
    wall = sum(durations.values()) + gaps
    return {'actions': len(rows), 'action_seconds': round(sum(durations.values()), 3),
            'planner_gap_seconds': round(gaps, 3),
            'confirmed_print_cells': cells,
            'confirmed_print_cells_per_minute': round(cells * 60 / wall, 3) if wall else 0,
            'by_operation': {k: {'count': counts[k], 'seconds': round(v, 3)}
                             for k, v in durations.most_common()},
            'warnings': warnings, 'scope': 'timing_only_not_placement_or_goal_credit'}


class ActionEfficiency:
    def __init__(self, out, prefix, world):
        self.path = Path(out) / (prefix + '-efficiency.jsonl')
        self.report = Path(out) / (prefix + '-efficiency.json')
        self.last_path = Path(out) / 'action-efficiency-last.json'
        self.world = world
        self.rows = []
        self.last_end = time.monotonic()
        # Include thinking/dispatch gaps between planners in the same world,
        # rather than hiding them whenever a new bounded plan is started.
        # A reboot, changed world or wall-clock jump cannot supply this metric.
        try:
            previous = json.loads(self.last_path.read_text())
            elapsed = self.last_end - previous['monotonic_end']
            wall_elapsed = time.time() - previous['wall_end']
            if (previous['world_session'] == world and math.isfinite(elapsed)
                    and 0 <= elapsed < 86400 and abs(elapsed - wall_elapsed) < 5):
                self.last_end = previous['monotonic_end']
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def record(self, action, params, started, ended, result=None, error=None):
        native = params.get('params') or {}
        row = {'world_session': self.world, 'time': time.time(),
               'op': params.get('op', action), 'action': action,
               'elapsed_seconds': round(ended - started, 6),
               'planner_gap_seconds': round(max(0, started - self.last_end), 6),
               'request_id': (result or {}).get('id'),
               'outcome': 'error' if error else 'returned',
               'mask_size': len(native.get('positions') or []) if params.get('op') == 'projection_batch_set' else 0}
        if error:
            row['error'] = error
        if row['op'] == 'professional_print' and result:
            from terminal_confirmation import verified
            if verified('professional_print', result, self.world, result.get('id'), {}):
                row['confirmed_print_cells'] = result['bounded_target_count']
        with self.path.open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.rows.append(row)
        self.last_end = ended
        write_json(self.last_path, {'world_session': self.world, 'monotonic_end': ended,
                                   'wall_end': time.time()})
        write_json(self.report, summarize(self.rows))
