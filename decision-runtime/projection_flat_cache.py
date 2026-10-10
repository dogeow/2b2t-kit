"""One full native baseline plus conserved, completed placement windows.

The saved ledger is a local material list, not a fresh full-world scan. Actual
observations are reused only by the same live controller; reconnects start a
new native baseline. Whole-map completion still requires a fresh native audit.
"""
from collections import Counter
from copy import deepcopy

from material_jobs.protocol import JobBlocked
from projection_flat_plan import position


class FlatMaterialLedger:
    def __init__(self, layout, audit, world):
        self.layout, self.world = layout, world
        self.actual = layout.observed(audit)
        self.audit = deepcopy(audit)
        self.baseline_at = audit['observed_at']
        self.windows = 0

    def accept(self, after, count, record, *, evidence_path):
        """Credit only the journal committed after ACK, scan, stock and cleanup."""
        points = record.get('physical_positions')
        if (record.get('complete') is not True or record.get('pending') is not None
                or record.get('world_session') != self.world
                or record.get('placement_key') != self.layout.key
                or not isinstance(points, list) or type(count) is not int or count < 1
                or len(points) != count
                or type(record.get('inventory_before')) is not int
                or type(record.get('inventory_after')) is not int
                or record['inventory_before'] - record['inventory_after'] != count):
            raise JobBlocked('缺料增量缺少完整施工窗口证明；保留原清单')
        changed = {position(p) for p in points}
        missing = {position(row['pos']): row for row in self.audit['mismatches']}
        if (len(changed) != count or not changed <= missing.keys()
                or changed & self.actual.keys()
                or set(after) - self.actual.keys() != changed
                or any(p not in self.layout.expected or v != self.layout.expected[p]['state']
                       or p in self.actual and self.actual[p] != v for p, v in after.items())):
            raise JobBlocked('缺料增量与已确认图面坐标不一致；不扣减材料')
        remaining = [row for row in self.audit['mismatches'] if position(row['pos']) not in changed]
        needs = Counter(self.layout.expected[position(row['pos'])]['item'] for row in remaining)
        value = dict(self.audit, matched=self.audit['matched'] + count,
                     mismatches=remaining, replacement_items=dict(sorted(needs.items())),
                     kinds={'missing': len(remaining)} if remaining else {},
                     actual_mismatch_blocks=dict(Counter('minecraft:' + row['actual'].split('minecraft:', 1)[1].split('}', 1)[0]
                                                         for row in remaining)),
                     material_ledger={'source': 'native_baseline_and_verified_windows',
                                      'world_session': self.world,
                                      'baseline_observed_at': self.baseline_at,
                                      'verified_windows': self.windows + 1,
                                      'last_window': str(evidence_path),
                                      'full_completion_verified': False})
        # observed_at deliberately remains the timestamp of the full baseline.
        self.layout.observed(value)
        self.actual.update(after)
        self.audit = value
        self.windows += 1
        return value
