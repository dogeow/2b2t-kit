"""Read-only repair classification and appearance checks for a translated projection.

No block is removed or entity spawned by this module. Historical audits cannot authorize
repairs: callers must refresh state, neighbor hazards, inventory and the safety lease.
"""
from collections import Counter
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

STATE = re.compile(r'^Block\{(minecraft:[a-z0-9_]+)\}(?:\[([^\]]+)\])?$')
TERRAIN = {'minecraft:stone', 'minecraft:dirt', 'minecraft:grass_block', 'minecraft:coal_ore'}


def block_state(text):
    match = STATE.fullmatch(text)
    if not match:
        raise ValueError('Unsupported block-state encoding')
    properties = {}
    for entry in (match[2] or '').split(','):
        if entry:
            key, value = entry.split('=', 1)
            if key in properties:
                raise ValueError('Duplicate state property')
            properties[key] = value
    return match[1], properties


def vector(value, integral=False):
    if not isinstance(value, list) or len(value) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value):
        raise ValueError('Expected three finite coordinates')
    if integral and any(int(v) != v for v in value):
        raise ValueError('Expected integer block coordinates')
    return list(value)


def classify(row):
    expected, ep = block_state(row['expected'])
    actual, ap = block_state(row['actual'])
    if row.get('fluid') or row.get('adjacent_fluid'):
        return 'fluid_review'
    if row.get('block_entity'):
        return 'preserve_container_or_block_entity'
    if row['kind'] == 'state_only':
        return 'refresh_connections_after_shell' if actual.endswith('glass_pane') else 'state_correction'
    if expected == 'minecraft:stripped_' + actual.removeprefix('minecraft:') and actual.endswith(('_log', '_wood', '_stem', '_hyphae')) and ep == ap:
        return 'strip_in_place'
    if row['kind'] == 'missing' and actual in ('minecraft:air', 'minecraft:cave_air', 'minecraft:void_air'):
        return 'place_missing'
    if actual in TERRAIN:
        return 'terrain_clear_candidate'
    return 'specific_block_repair'


def repair_plan(audit, selection):
    if audit['placement_key'] != selection['key']:
        raise ValueError('Projection placement changed')
    low, high = vector(selection['min'], True), vector(selection['max'], True)
    if audit['matched'] + len(audit['mismatches']) != audit['total']:
        raise ValueError('Incomplete non-air block audit')
    groups = {}
    seen = set()
    rows = audit['mismatches'] + audit.get('enclosed_air_conflicts', [])
    for row in rows:
        pos = vector(row['pos'], True)
        if tuple(pos) in seen or any(v < a or v > b for v, a, b in zip(pos, low, high)):
            raise ValueError('Duplicate or out-of-scope repair position')
        seen.add(tuple(pos))
        category = classify(row)
        entry = {**row, 'needs_fresh_state_check': True,
                 'needs_neighbor_rescan': not row.get('neighbors_loaded', False),
                 'never_remove_player_footing': True}
        if category == 'strip_in_place':
            entry['operation'] = 'axe_use_on_existing_log'
            entry['new_material_required'] = False
        if category == 'terrain_clear_candidate':
            entry['requires_checked_access_and_support'] = True
            entry['requires_replacement_ready'] = row['expected'] != 'Block{minecraft:air}'
        if category == 'preserve_container_or_block_entity':
            entry['inventory_policy'] = 'preserve_all_contents; inspect before any structural correction'
        groups.setdefault(category, []).append(entry)
    return {'schema': 1, 'placement_key': selection['key'], 'planning_only': True,
            'source_audit_observed_at': audit.get('observed_at'), 'non_air_matched': audit['matched'],
            'non_air_total': audit['total'], 'groups': groups,
            'group_counts': {key: len(rows) for key, rows in groups.items()},
            'interior_air_checked': audit.get('audit_schema', 0) >= 2 and 'enclosed_air_conflicts' in audit and audit.get('loaded_chunks_verified') is True,
            'air_check_scope': 'enclosed_voxels_only; open corridors still need access verification',
            'requires_live_appearance_audit': True, 'safe_to_execute_without_revalidation': False}


def decoration_manifest(specials, selection, region, variants=None):
    # This task's House region is unrotated, positive-sized and starts at zero.
    # Do not silently apply the wrong transform to a different placement.
    if not selection['key'].endswith('/NONE/NONE') or region['position'] != [0, 0, 0]:
        raise ValueError('Only an explicitly verified zero-origin translated region is supported')
    origin, high = vector(selection['min'], True), vector(selection['max'], True)
    size = vector(region['size'], True)
    if any(n <= 0 or hi - lo + 1 != n for lo, hi, n in zip(origin, high, size)):
        raise ValueError('Schematic region and selected bounds differ')
    def world(pos):
        local = vector(pos)
        if any(p < 0 or p >= n for p, n in zip(local, size)):
            raise ValueError('Decoration outside source region')
        return [o + p for o, p in zip(origin, local)]
    entities = []
    requirements = Counter()
    for i, entity in enumerate(specials['entities']):
        kind = entity['id']
        if kind not in ('minecraft:armor_stand', 'minecraft:item_frame', 'minecraft:glow_item_frame', 'minecraft:painting'):
            raise ValueError('Unsupported schematic entity; explicit adapter required')
        row = {'index': i, 'type': kind, 'pos': world(entity['Pos']), 'invisible': bool(entity.get('Invisible', False))}
        requirements[kind] += 1
        if kind.endswith('item_frame'):
            item = entity.get('Item', {'id': 'minecraft:air', 'count': 0})
            row.update(facing=int(entity['Facing']), item_rotation=int(entity.get('ItemRotation', 0)),
                       item={'id': item['id'], 'count': item.get('count', 1)})
            if item['id'].endswith('_banner'):
                row['item']['patterns'] = item.get('components', {}).get('minecraft:banner_patterns', [])
            if item['id'] != 'minecraft:air':
                requirements[item['id']] += item.get('count', 1)
        elif kind == 'minecraft:armor_stand':
            row.update(yaw=entity.get('Rotation', [0, 0])[0], small=bool(entity.get('Small', False)),
                       show_arms=bool(entity.get('ShowArms', False)), base_plate=not bool(entity.get('NoBasePlate', False)),
                       default_pose=not bool(entity.get('Pose')))
            if entity.get('Pose'):
                row['unsupported_check'] = 'custom armor stand pose'
        else:
            row.update(facing=int(entity['facing']), variant=entity['variant'])
            if variants and entity['variant'] in variants:
                row.update({k: variants[entity['variant']][k] for k in ('width', 'height')})
        entities.append(row)
    banners = [{'pos': world([b['x'], b['y'], b['z']]), 'patterns': b.get('patterns', [])}
               for b in specials['tile_entities'] if b['id'] == 'minecraft:banner']
    return {'schema': 1, 'placement_key': selection['key'], 'schematic_sha256': specials['sha256'],
            'transform': 'translation_only', 'entities': entities, 'banners': banners,
            'items_before_subtracting_verified_existing_entities': dict(requirements),
            'container_inventory_policy': 'preserve existing contents; empty schematic inventories are not a deletion request'}


def compare_decorations(manifest, audit):
    if manifest['placement_key'] != audit['placement_key']:
        raise ValueError('Decoration audit belongs to another placement')
    results = []
    used = set()
    def close(a, b):
        return sum((x-y)**2 for x,y in zip(vector(a),vector(b))) <= .2**2
    for expected in manifest['entities']:
        base = {'index': expected['index'], 'type': expected['type'], 'pos': expected['pos']}
        if audit.get('audit_schema', 0) < 2 or 'decorations' not in audit:
            results.append({**base, 'status': 'unverified', 'reason': 'No full decoration observation'});continue
        candidates = [(i, actual) for i, actual in enumerate(audit['decorations']) if i not in used and actual['type'] == expected['type'] and close(actual['pos'],expected['pos'])]
        if len(candidates) != 1:
            results.append({**base, 'status': 'not_observed' if not candidates else 'ambiguous',
                            'reason': 'Move close and re-observe before placing or removing anything'});continue
        index, actual = candidates[0];used.add(index)
        differing = []
        unknown = []
        for key, value in expected.items():
            if key in ('index', 'type', 'pos'):continue
            if key == 'unsupported_check' or key not in actual:
                unknown.append(key);continue
            matches = abs((actual[key]-value+180)%360-180) < 2 if key == 'yaw' else actual[key] == value
            if not matches:differing.append(key)
        results.append({**base, 'status': 'different' if differing else 'unverified' if unknown else 'matched',
                        'different_fields': differing, 'unverified_fields': unknown})
    banner_results=[]
    for expected in manifest['banners']:
        observed = [b for b in audit.get('banners', []) if close(b['pos'],expected['pos'])]
        state = 'unverified' if audit.get('audit_schema',0)<2 else 'not_observed' if not observed else 'ambiguous' if len(observed)>1 else 'matched' if observed[0].get('patterns') == expected['patterns'] else 'different'
        banner_results.append({'pos':expected['pos'],'status':state})
    return {'entity_checks': results, 'banner_checks': banner_results,
            'all_observed_appearance_matches': all(r['status']=='matched' for r in results+banner_results),
            'entity_coverage': audit.get('entity_coverage','unavailable'),
            'automatic_removal_authorized': False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',type=Path,required=True);p.add_argument('--selection-snapshot',type=Path,required=True)
    p.add_argument('--specials',type=Path,required=True);p.add_argument('--region',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();audit=json.loads(args.audit.read_text());selection=json.loads(args.selection_snapshot.read_text())['projection_selection']
    specials=json.loads(args.specials.read_text());region=json.loads(args.region.read_text())
    if hashlib.sha256(Path(specials['path']).read_bytes()).hexdigest()!=specials['sha256']:
        raise ValueError('Schematic changed since the special-data extraction')
    manifest=decoration_manifest(specials,selection,region,region.get('painting_variants'))
    out={'repairs':repair_plan(audit,selection),'decorations':manifest,'appearance':compare_decorations(manifest,audit),
         'complete':False,'reason':'Requires fresh world, enclosed-air, appearance and safe-player verification'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps({'repair_counts':out['repairs']['group_counts'],'decorations':len(manifest['entities']),
                      'banners':len(manifest['banners']),'interior_air_checked':out['repairs']['interior_air_checked'],
                      'complete':False},ensure_ascii=False))

if __name__=='__main__':main()
