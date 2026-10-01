"""Bounded coarse snow-biome discovery over client-loaded chunks only."""
from __future__ import annotations

import math
import re


VERSION = 1
ANCHOR_STRIDE = 128
SURVEY_RADIUS = 64
SAMPLE_STRIDE = 64
MAX_ANCHORS_PER_CALL = 4
LEDGER_KEY = 'snow_biome_search'
_CELL_KEY = re.compile(r'-?[0-9]+:-?[0-9]+')


def anchors(origin, radius, stride=ANCHOR_STRIDE):
    """Return a deterministic, bounded ring order of high-flight waypoints."""
    if (not isinstance(origin, (list, tuple)) or len(origin) != 3
            or any(type(value) not in (int, float) or not math.isfinite(value)
                   for value in origin)
            or type(radius) is not int or radius < 1 or radius > 384
            or type(stride) is not int or stride < 64 or stride > 192):
        raise ValueError('Invalid coarse snow-biome search bounds')
    if radius < 16:
        return []
    base_x = math.floor(origin[0] / 16) * 16 + 8
    base_z = math.floor(origin[2] / 16) * 16 + 8
    limit = math.ceil(radius / stride)
    result = []
    for ring in range(limit + 1):
        if ring == 0:
            offsets = [(0, 0)]
        else:
            offsets = [(dx, -ring) for dx in range(-ring, ring + 1)]
            offsets += [(ring, dz) for dz in range(-ring + 1, ring + 1)]
            offsets += [(dx, ring) for dx in range(ring - 1, -ring - 1, -1)]
            offsets += [(-ring, dz) for dz in range(ring - 1, -ring, -1)]
        for dx, dz in offsets:
            x, z = base_x + dx * stride, base_z + dz * stride
            if math.hypot(x + .5 - origin[0], z + .5 - origin[2]) <= radius:
                result.append((x, z))
    return result


def ledger_state(ledger):
    """Create or strictly validate the persistent coarse-search namespace."""
    value = ledger.get(LEDGER_KEY)
    if value is None:
        value = {'version': VERSION, 'anchor_stride': ANCHOR_STRIDE,
                 'survey_radius': SURVEY_RADIUS, 'sample_stride': SAMPLE_STRIDE,
                 'visited': {}, 'candidates': {}}
        ledger[LEDGER_KEY] = value
        return value
    if (not isinstance(value, dict) or value.get('version') != VERSION
            or value.get('anchor_stride') != ANCHOR_STRIDE
            or value.get('survey_radius') != SURVEY_RADIUS
            or value.get('sample_stride') != SAMPLE_STRIDE
            or not isinstance(value.get('visited'), dict)
            or not isinstance(value.get('candidates'), dict)
            or any(not isinstance(key, str) or not isinstance(entry, dict)
                   for field in ('visited', 'candidates')
                   for key, entry in value[field].items())):
        raise RuntimeError('雪地粗筛记录格式损坏；保留现场，不覆盖旧记录')
    for key,entry in value['visited'].items():
        anchor=entry.get('anchor')
        if (not _CELL_KEY.fullmatch(key)
                or not isinstance(anchor,list) or len(anchor)!=2
                or any(type(point) is not int for point in anchor)
                or key!=f'{anchor[0]}:{anchor[1]}'
                or entry.get('state') not in
                    ('cold_candidates','loaded_no_cold_sample',
                     'loaded_cold_protected','no_loaded_samples')
                or not isinstance(entry.get('world_session'),str)
                or not entry['world_session']
                or type(entry.get('observed_at')) not in (int,float)
                or not math.isfinite(entry['observed_at'])
                or type(entry.get('loaded_samples')) is not int
                or type(entry.get('unloaded_samples')) is not int
                or entry['loaded_samples']<0 or entry['unloaded_samples']<0
                or entry['loaded_samples']+entry['unloaded_samples']!=9
                or ('candidate_tiles' in entry
                    and (not isinstance(entry['candidate_tiles'],list)
                         or any(not isinstance(tile,str) or not _CELL_KEY.fullmatch(tile)
                                for tile in entry['candidate_tiles'])))):
            raise RuntimeError('雪地粗筛访问记录损坏；保留现场，不覆盖旧记录')
    for key,entry in value['candidates'].items():
        tile=entry.get('tile');sample=entry.get('sample')
        if (not _CELL_KEY.fullmatch(key)
                or not isinstance(tile,list) or len(tile)!=2
                or any(type(point) is not int for point in tile)
                or key!=f'{tile[0]}:{tile[1]}'
                or not isinstance(sample,list) or len(sample)!=3
                or any(type(point) is not int for point in sample)
                or not isinstance(entry.get('biome'),str) or not entry['biome']
                or entry.get('precipitation') not in ('none','rain','snow')
                or type(entry.get('cold_enough_to_snow')) is not bool):
            raise RuntimeError('雪地粗筛候选记录损坏；保留现场，不覆盖旧记录')
    return value


def parse_reply(reply, request_id, world_session, center,
                radius=SURVEY_RADIUS, stride=SAMPLE_STRIDE):
    """Validate that a reply belongs to the just-issued read-only survey."""
    if (not isinstance(reply, dict) or reply.get('phase') not in (None, 'done')
            or reply.get('id') != request_id
            or reply.get('world_session') != world_session):
        raise ValueError('雪地群系粗筛回执不属于当前只读请求')
    survey = reply.get('snow_biome_survey')
    if (not isinstance(survey, dict) or survey.get('center') != list(center)
            or survey.get('radius') != radius or survey.get('stride') != stride
            or type(survey.get('requested_samples')) is not int
            or type(survey.get('loaded_samples')) is not int
            or type(survey.get('unloaded_samples')) is not int
            or not isinstance(survey.get('samples'), list)):
        raise ValueError('雪地群系粗筛回执缺少完整范围与计数')
    requested = survey['requested_samples']
    loaded = survey['loaded_samples']
    unloaded = survey['unloaded_samples']
    rows = survey['samples']
    expected=((2 * radius) // stride + 1) ** 2
    if (requested != expected or not 0 < requested <= 169
            or loaded != len(rows) or unloaded < 0
            or requested != loaded + unloaded):
        raise ValueError('雪地群系粗筛回执计数不一致')
    seen = set()
    for row in rows:
        pos = row.get('pos') if isinstance(row, dict) else None
        chunk = row.get('chunk') if isinstance(row, dict) else None
        if (not isinstance(pos, list) or len(pos) != 3
                or any(type(value) is not int for value in pos)
                or not isinstance(chunk, list) or len(chunk) != 2
                or any(type(value) is not int for value in chunk)
                or chunk != [pos[0] // 16, pos[2] // 16]
                or not center[0] - radius <= pos[0] <= center[0] + radius
                or not center[1] - radius <= pos[2] <= center[1] + radius
                or (pos[0] - (center[0] - radius)) % stride
                or (pos[2] - (center[1] - radius)) % stride
                or not -64 <= pos[1] <= 319
                or not isinstance(row.get('biome'), str) or not row['biome']
                or row.get('precipitation') not in ('none', 'rain', 'snow')
                or type(row.get('cold_enough_to_snow')) is not bool
                or type(row.get('base_temperature')) not in (int, float)
                or not math.isfinite(row['base_temperature'])):
            raise ValueError('雪地群系粗筛样点格式或范围无效')
        point = (pos[0], pos[2])
        if point in seen:
            raise ValueError('雪地群系粗筛包含重复样点')
        seen.add(point)
    return survey


def cold_tiles(samples, allowed_tiles):
    """Map only positively observed cold/snow samples to detailed 16x16 tiles."""
    allowed = set(allowed_tiles)
    found = {}
    for row in samples:
        if not (row['cold_enough_to_snow'] or row['precipitation'] == 'snow'):
            continue
        x, y, z = row['pos']
        tile = (math.floor(x / 16) * 16, math.floor(z / 16) * 16)
        if tile not in allowed:
            continue
        found[f'{tile[0]}:{tile[1]}'] = {
            'tile': [tile[0], tile[1]], 'sample': [x, y, z],
            'biome': row['biome'], 'precipitation': row['precipitation'],
            'cold_enough_to_snow': row['cold_enough_to_snow']}
    return found
