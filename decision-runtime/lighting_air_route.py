"""Pure, bounded low-altitude flight planning within one complete scan box.

The caller must have verified that ``cells`` contains every non-AIR cell in
the inclusive ``low``/``high`` box. Only omissions *inside that box* mean AIR;
any present row is occupied, irrespective of its material or passability.
Live movement must still rescan each returned leg before dispatching input.
"""
from __future__ import annotations

from functools import lru_cache
from heapq import heappop, heappush
from itertools import permutations, product
import math


_HALF_WIDTH = .35
_HEIGHT = 1.8
_CLEARANCE_CACHE = 4096
_HARD_EXPANSIONS = 32_000
_DIRECTIONS = ((0, -1, 0), (1, 0, 0), (-1, 0, 0),
               (0, 0, 1), (0, 0, -1), (0, 1, 0))


def _point(value, *, integer=False):
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        return None
    result = []
    for component in value:
        if type(component) not in ((int,) if integer else (int, float)):
            return None
        try:
            numeric = float(component)
        except (OverflowError, ValueError):
            return None
        # Half-cell centers must remain exactly representable. Minecraft's
        # legal coordinates are far below this floating-point limit.
        if not math.isfinite(numeric) or abs(numeric) >= 2 ** 51:
            return None
        result.append(component if integer else numeric)
    return tuple(result)


def _xyz(node):
    return tuple(component + .5 for component in node)


def _axis(a, b):
    changed = [i for i in range(3) if a[i] != b[i]]
    return changed[0] if len(changed) == 1 else None


def _compress(points):
    """Remove only same-direction collinear steps; retain every axis turn."""
    result = []
    for point in points:
        if result and point == result[-1]:
            continue
        if len(result) >= 2:
            previous_axis = _axis(result[-2], result[-1])
            next_axis = _axis(result[-1], point)
            if (previous_axis is not None and previous_axis == next_axis
                    and (result[-1][next_axis] - result[-2][next_axis])
                    * (point[next_axis] - result[-1][next_axis]) > 0):
                result[-1] = point
                continue
        result.append(point)
    return [list(point) for point in result]


def plan(cells, start, target, low, high, max_expansions=32_000):
    """Return exact start/target plus compressed axis-only waypoints, or None.

    Search uses half-cell centered feet positions with .35 horizontal
    half-width and 1.8 body height, covering three Y cells at each node. Every
    intermediate node has one additional cell of horizontal clearance; exact
    endpoints need only their actual body clearance. Nearby off-center poses
    are connected to the lattice by separately checked, axis-only legs.

    Horizontal height cost prefers the lower endpoint's altitude. This makes
    a high start descend before flat travel without encouraging gratuitous
    dives below an already low target. Obstacles can require an observed low
    detour or a local rise before their padded corridor. Search never exceeds
    32,000 expanded nodes, even if a larger budget is requested. Invalid input,
    an obstructed/unknown body sweep, or an exhausted budget returns None.
    """
    low, high = _point(low, integer=True), _point(high, integer=True)
    start, target = _point(start), _point(target)
    if (not isinstance(cells, dict) or low is None or high is None
            or start is None or target is None
            or any(low[i] > high[i] for i in range(3))
            or type(max_expansions) is not int or max_expansions <= 0):
        return None
    for cell in cells:
        if (not isinstance(cell, tuple) or _point(cell, integer=True) is None
                or any(not low[i] <= cell[i] <= high[i] for i in range(3))):
            return None
    budget = min(max_expansions, _HARD_EXPANSIONS)

    def sweep_clear(a, b, padding=0):
        if a != b and _axis(a, b) is None:
            return False
        minimum = tuple(math.floor(min(a[i], b[i])
                                   - (_HALF_WIDTH + padding if i != 1 else 0))
                        for i in range(3))
        maximum = tuple(math.floor(max(a[i], b[i])
                                   + (_HALF_WIDTH + padding if i != 1 else _HEIGHT))
                        for i in range(3))
        if any(minimum[i] < low[i] or maximum[i] > high[i] for i in range(3)):
            return False
        return all((x, y, z) not in cells
                   for x in range(minimum[0], maximum[0] + 1)
                   for y in range(minimum[1], maximum[1] + 1)
                   for z in range(minimum[2], maximum[2] + 1))

    if not sweep_clear(start, start) or not sweep_clear(target, target):
        return None
    if start == target:
        return [list(start)]

    def alignment(pose, node):
        center = _xyz(node)
        if not sweep_clear(center, center):
            return None
        axes = tuple(i for i in range(3) if pose[i] != center[i])
        for order in permutations(axes):
            points = [pose]
            for axis in order:
                next_point = list(points[-1])
                next_point[axis] = center[axis]
                next_point = tuple(next_point)
                if not sweep_clear(points[-1], next_point):
                    break
                points.append(next_point)
            else:
                return points
        return None

    def aligned_node(pose, other):
        # Integer poses are equally near two centers. Prefer a lower center
        # rather than introducing a half-block ascent before a descent. Also
        # permit another center within .6 on each axis when the closest center
        # expands the body into an observed ceiling or neighboring block.
        nearby = [tuple(n for n in range(math.floor(v) - 1, math.floor(v) + 2)
                        if abs(n + .5 - v) <= .6) for v in pose]
        nodes = sorted(product(*nearby), key=lambda node: (
            sum((node[i] + .5 - pose[i]) ** 2 for i in range(3)), node[1],
            abs(node[0] + .5 - other[0]) + abs(node[2] + .5 - other[2]), node))
        for node in nodes:
            points = alignment(pose, node)
            if points is not None:
                return node, points
        return None

    aligned_start = aligned_node(start, target)
    aligned_target = aligned_node(target, start)
    if aligned_start is None or aligned_target is None:
        return None
    start_node, initial = aligned_start
    target_node, final = aligned_target
    if start_node == target_node:
        return _compress(initial + list(reversed(final))[1:])

    @lru_cache(maxsize=_CLEARANCE_CACHE)
    def node_clear(node):
        padding = 0 if node in (start_node, target_node) else 1
        center = _xyz(node)
        return sweep_clear(center, center, padding)

    preferred_y = min(start_node[1], target_node[1])

    def heuristic(node):
        horizontal = abs(node[0] - target_node[0]) + abs(node[2] - target_node[2])
        dy = target_node[1] - node[1]
        return horizontal + (dy * 1.25 if dy > 0 else -dy)

    frontier = [(heuristic(start_node), 0.0, 0, start_node)]
    costs = {start_node: 0.0}
    parents = {}
    expanded = 0
    sequence = 0
    while frontier and expanded < budget:
        _, cost, _, node = heappop(frontier)
        if cost != costs.get(node):
            continue
        expanded += 1
        if node == target_node:
            route = [node]
            while route[-1] != start_node:
                route.append(parents[route[-1]])
            route.reverse()
            return _compress(initial + [_xyz(p) for p in route[1:]]
                             + list(reversed(final))[1:])
        for dx, dy, dz in _DIRECTIONS:
            neighbor = (node[0] + dx, node[1] + dy, node[2] + dz)
            if not node_clear(neighbor):
                continue
            # Adjacent centered axis moves occupy only the actual body cells
            # of their endpoints, both of which were checked above. No diagonal
            # or rectangular start-to-goal shortcut is permitted.
            step = (1.25 if dy > 0 else 1.0) if dy else (
                1.0 + .18 * max(0, node[1] - preferred_y))
            next_cost = cost + step
            if next_cost >= costs.get(neighbor, math.inf):
                continue
            costs[neighbor] = next_cost
            parents[neighbor] = node
            sequence += 1
            heappush(frontier, (next_cost + heuristic(neighbor), next_cost,
                                sequence, neighbor))
    return None
