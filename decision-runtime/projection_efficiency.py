"""Lightweight diagnostics from completed windows; no game actions or tuning."""
from collections import deque
from statistics import median


class WindowEfficiency:
    def __init__(self):
        self.records = deque(maxlen=12)
        self.completed = 0

    def add(self, record):
        positions = record.get('physical_positions') or []
        elapsed, travel = record.get('elapsed_seconds'), record.get('travel_seconds')
        if (record.get('complete') is not True or record.get('pending') is not None or not positions
                or type(elapsed) not in (int,float) or type(travel) not in (int,float)
                or not 0 <= travel <= elapsed <= 1800):
            return None
        self.records.append({'placed': len(positions), 'elapsed': elapsed, 'travel': travel})
        self.completed += 1
        if self.completed % 3:
            return None
        total = sum(r['elapsed'] for r in self.records)
        cells = sum(r['placed'] for r in self.records)
        share = sum(r['travel'] for r in self.records) / total if total else 0
        findings = []
        if share > .5:
            findings.append('travel_dominates_review_registered_direct_routes')
        if median(r['placed'] for r in self.records) <= 3:
            findings.append('small_windows_review_grouping_within_normal_reach')
        return {'schema': 1, 'evidence_scope': 'timing_of_completed_conserved_windows',
                'sample_windows': len(self.records), 'confirmed_cells': cells,
                'seconds_per_cell': round(total/cells,3), 'travel_share': round(share,3),
                'findings': findings, 'automatic_parameter_changes': False,
                'review_requires_real_comparison_before_promoting': True}
