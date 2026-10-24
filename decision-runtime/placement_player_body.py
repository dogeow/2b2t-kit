"""Conservative pre-use guard for the standing operator and full-cube placements."""
import math

FULL_ITEMS = frozenset('minecraft:' + name for name in (
    'cobblestone', 'dark_oak_planks', 'cherry_planks', 'oak_planks',
    'stone', 'stone_bricks', 'polished_andesite', 'dirt', 'grass_block',
))


def require_player_clear(state, target, item):
    if item not in FULL_ITEMS:
        return
    point = state.get('pos')
    if (not isinstance(point, list) or len(point) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in point)):
        raise ValueError('Current operator position is unavailable')
    low = [point[0] - .3, point[1], point[2] - .3]
    high = [point[0] + .3, point[1] + 1.8, point[2] + .3]
    if all(high[i] > target[i] + 1e-7 and low[i] < target[i] + 1 - 1e-7 for i in range(3)):
        raise ValueError('Operator body overlaps the placement cell; move clear before use')
