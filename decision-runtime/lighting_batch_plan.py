"""Predict a small exterior-lighting batch from one complete loaded scan.

The caller must obtain and verify a complete detailed non-AIR scan before
calling this pure planner. Missing cells are known AIR only inside that scan
box. Predictions never acknowledge placement or replace the final live audit.
"""
from __future__ import annotations

import math
import re

import lighting_cli as lighting

TORCH_LEVEL = 14
MAX_BATCH = 8
_AIR = frozenset(('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'))
# Minecraft 26.1.2: these exact unfluidized states have light dampening 0
# and no light-face occlusion. They only transmit predicted light; they are
# never promoted to AIR for candidates, placement, clearance, or movement.
_LIGHT_TRANSMITTING_STATES = frozenset((
    'Block{minecraft:short_grass}', 'Block{minecraft:dandelion}',
))
_BOOLEAN_DETAILS = ('solid', 'fluid', 'block_entity', 'zombie_spawn_floor',
                    'zombie_block_light_risk')
_LIGHT_DETAILS = ('spawn_block_light', 'monster_spawn_block_light_limit')
_STATE = re.compile(r'Block\{[a-z0-9_.-]+:[a-z0-9_./-]+\}(?:\[[^\r\n\[\]]*\])?')


def _observations(cells, low, high):
    """Fail closed on incomplete details; never turn omitted flags into safety."""
    if not isinstance(cells, dict):
        raise lighting.LightingBlocked('Complete detailed non-AIR cells unavailable')
    for key, row in cells.items():
        try:
            pos = lighting.point(key)
            observed = lighting.point(row.get('pos')) if isinstance(row, dict) else None
        except ValueError as exc:
            raise lighting.LightingBlocked('Malformed lighting scan position') from exc
        if (observed != pos or any(not low[i] <= pos[i] <= high[i] for i in range(3))
                or not isinstance(row, dict)):
            raise lighting.LightingBlocked('Inconsistent or out-of-bounds lighting scan cell')
        state = row.get('state')
        if (not isinstance(state, str) or _STATE.fullmatch(state) is None
                or lighting.block_id(row) in _AIR):
            raise lighting.LightingBlocked('Exact non-AIR lighting scan state unavailable')
        if (any(type(row.get(name)) is not bool for name in _BOOLEAN_DETAILS)
                or any(type(row.get(name)) is not int or not 0 <= row[name] <= 15
                       for name in _LIGHT_DETAILS)):
            raise lighting.LightingBlocked('Complete detailed lighting observations unavailable')
        if (row['zombie_block_light_risk'] and (not row['zombie_spawn_floor']
                or row['spawn_block_light'] > row['monster_spawn_block_light_limit'])):
            raise lighting.LightingBlocked('Inconsistent observed dark spawn-floor risk')


def _light_transmitting(row):
    return (row['state'] in _LIGHT_TRANSMITTING_STATES
            and row['fluid'] is False and row['block_entity'] is False
            and row['solid'] is False and row.get('passable') is True)


class _LightGrid:
    """Bounded light paths through known AIR and two verified plant states."""
    def __init__(self, cells, low, high, protected):
        self.low, self.high = low, high
        self.ny, self.nz = high[1] - low[1] + 1, high[2] - low[2] + 1
        self.x_stride = self.ny * self.nz
        self.size = (high[0] - low[0] + 1) * self.x_stride
        self.transmits = bytearray(b'\x01') * self.size
        for pos, row in cells.items():
            self.transmits[self.index(pos)] = int(_light_transmitting(row))
        # Protected footprints are outside this conservative prediction domain.
        for box in protected:
            minimum = [max(low[i], box['min'][i]) for i in range(3)]
            maximum = [min(high[i], box['max'][i]) for i in range(3)]
            for x in range(minimum[0], maximum[0] + 1):
                for y in range(minimum[1], maximum[1] + 1):
                    if minimum[2] <= maximum[2]:
                        first = self.index((x, y, minimum[2]))
                        width = maximum[2] - minimum[2] + 1
                        self.transmits[first:first + width] = b'\x00' * width
        self.adjacent = [()] * self.size
        for x in range(high[0] - low[0] + 1):
            for y in range(self.ny):
                for z in range(self.nz):
                    here = x * self.x_stride + y * self.nz + z
                    if not self.transmits[here]:
                        continue
                    options = []
                    if x:
                        options.append(here - self.x_stride)
                    if x < high[0] - low[0]:
                        options.append(here + self.x_stride)
                    if y:
                        options.append(here - self.nz)
                    if y < self.ny - 1:
                        options.append(here + self.nz)
                    if z:
                        options.append(here - 1)
                    if z < self.nz - 1:
                        options.append(here + 1)
                    self.adjacent[here] = tuple(nxt for nxt in options if self.transmits[nxt])
        self.visited = [0] * self.size
        self.stamp = 0

    def contains(self, pos):
        return all(self.low[i] <= pos[i] <= self.high[i] for i in range(3))

    def index(self, pos):
        return ((pos[0] - self.low[0]) * self.x_stride
                + (pos[1] - self.low[1]) * self.nz + pos[2] - self.low[2])

    def coverage(self, target, risk_at):
        """Every allowed light-path edge, including a plant, attenuates by one."""
        first = self.index(target)
        if not self.transmits[first]:
            return 0
        self.stamp += 1
        stamp, visited, adjacent = self.stamp, self.visited, self.adjacent
        frontier, covered = [first], 0
        visited[first] = stamp
        for distance in range(TORCH_LEVEL):
            following = []
            for here in frontier:
                observed = risk_at.get(here)
                if observed is not None and TORCH_LEVEL - distance > observed[1]:
                    covered |= observed[0]
                if distance < TORCH_LEVEL - 1:
                    for nxt in adjacent[here]:
                        if visited[nxt] != stamp:
                            visited[nxt] = stamp
                            following.append(nxt)
            if not following:
                break
            frontier = following
        return covered


def plan(cells, low, high, start, protected=None, limit=MAX_BATCH, *, residual=True):
    """Return ordered placement-compatible candidates, with prediction counts.

    Candidate/support checks and observed risk counts each run once on the
    original snapshot. Greedy coverage uses in-bounds known light paths and
    positive torch light; equal coverage prefers the nearest next station.
    Exact support state is preserved for the caller's narrow live preflight.
    """
    low, high = lighting.bounds(low, high)
    if type(limit) is not int or not 1 <= limit <= MAX_BATCH:
        raise ValueError('Lighting batch limit must be 1..8')
    if (not isinstance(start, (list, tuple)) or len(start) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in start)):
        raise ValueError('Lighting batch start needs three finite coordinates')
    protected = lighting.protection_boxes(protected)
    _observations(cells, low, high)
    counts = lighting.risk_counts(cells, protected)
    if type(residual)is not bool:
        raise ValueError('Residual neighbor lighting mode must be boolean')
    options = lighting.candidates(cells,low,high,start,protected,include_lit=residual)
    if not counts['unprotected_dark_floor'] or not options:
        return []
    grid = _LightGrid(cells, low, high, protected)
    risk_at = {}
    for support, row in cells.items():
        target = (support[0], support[1] + 1, support[2])
        if (row['zombie_block_light_risk'] and grid.contains(target)
                and not lighting.candidate_protected(support, target, protected)
                and grid.transmits[grid.index(target)]):
            risk_at[grid.index(target)] = (1 << len(risk_at), row['monster_spawn_block_light_limit'])
    remaining = (1 << len(risk_at)) - 1
    predicted = [(dict(candidate), grid.coverage(candidate['target'], risk_at)) for candidate in options]
    ordered, station = [], start
    while remaining and predicted and len(ordered) < limit:
        best, best_key = None, None
        for index, (candidate, coverage) in enumerate(predicted):
            gain = (coverage & remaining).bit_count()
            if not gain:
                continue
            support = candidate['support']
            distance = math.dist(station, (support[0] + .5, support[1] + 2.5, support[2] + .5))
            key = (-gain, distance, tuple(support))
            if best_key is None or key < best_key:
                best, best_key = index, key
        if best is None:
            break
        candidate, coverage = predicted.pop(best)
        candidate['distance'] = best_key[1]
        candidate['predicted_coverage_count'] = -best_key[0]
        candidate['placement_basis']=('safe_neighbor_of_observed_dark_floor'
            if not cells[tuple(candidate['support'])]['zombie_block_light_risk']else'observed_dark_safe_support')
        candidate['prediction_only']=True
        ordered.append(candidate)
        remaining &= ~coverage
        support = candidate['support']
        station = (support[0] + .5, support[1] + 2.5, support[2] + .5)
    return ordered
