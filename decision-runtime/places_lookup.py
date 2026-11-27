"""Read-only list of the player's saved places and last death point from the Kit config.

Saved places carry no server scope in the config, so this reports them as recorded and adds the
horizontal distance from the player when a live status with a position is available.
"""
import json
import math
from pathlib import Path


def _distance(place, here, dimension):
    if not here or place.get('dimension') != dimension:
        return None
    return round(math.hypot(place['x'] - here[0], place['z'] - here[2]))


def lookup(config, state=None, match=''):
    state = state or {}
    here = state.get('pos') if isinstance(state.get('pos'), list) and len(state['pos']) == 3 else None
    dimension = state.get('dimension')
    needle = (match or '').strip().lower()
    rows = []
    for place in config.get('savedPlaces') or []:
        if not isinstance(place, dict) or not isinstance(place.get('x'), (int, float)) or not isinstance(place.get('z'), (int, float)):
            continue
        name = str(place.get('name', ''))
        if needle and needle not in name.lower():
            continue
        row = {'name': name, 'x': place['x'], 'z': place['z'], 'cruise_y': place.get('cruiseY'),
               'dimension': place.get('dimension'), 'home': bool(place.get('home'))}
        distance = _distance(place, here, dimension)
        if distance is not None:
            row['distance'] = distance
        rows.append(row)
    rows.sort(key=lambda r: (not r['home'], r.get('distance', math.inf), r['name']))
    out = {'schema': 1, 'places': rows}
    if config.get('hasDeathPoint') and not needle:
        out['death'] = {k: config.get(c) for k, c in (('x', 'deathX'), ('y', 'deathY'), ('z', 'deathZ'),
                        ('dimension', 'deathDimension'), ('killer', 'deathKiller'), ('at', 'deathTimeEpochMillis'))}
    out['note'] = '地点是本地记录，没有区分服务器；出发前确认当前服务器与维度'
    return out


def read_config(game_dir):
    return json.loads(Path(game_dir, 'config/twob2tkit.json').read_text())
