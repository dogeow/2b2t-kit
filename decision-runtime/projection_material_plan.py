"""Read-only net material planning from a projection comparison and explicit stock audit.

Usage: python projection_material_plan.py --jar CLIENT.jar --projection audit.json
       --stock stock.json [--output plan.json]

Stock format: {"complete": true, "sources": [{"key": "backpack",
"kind": "carried", "observed_at": 123, "complete": true,
"counts": {"minecraft:furnace": 17}}]}.
Use kind "depot" for freshly inspected containers, "installed" for placed
equipment, and "historical" for unverified records. Only carried/depot stock
observed at or after the projection comparison is counted. A depot count is
available stock, never evidence that it has already reached the backpack.
No game client, network, model call, or automation state is used by this module.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import zipfile

from material_plan import MaterialPlanner, quantities
from recipe_catalog import Recipe, RecipeCatalog


class ProcessingCatalog(RecipeCatalog):
    """Reuse the crafting planner with ordinary furnace recipes from the same JAR."""
    def __init__(self, jar):
        super().__init__(jar)
        self.smelting = {}
        with zipfile.ZipFile(self.jar) as archive:
            for name in archive.namelist():
                if not name.startswith('data/minecraft/recipe/') or not name.endswith('.json'):
                    continue
                data = json.loads(archive.read(name))
                if data.get('type') != 'minecraft:smelting':
                    continue
                result = data.get('result', {})
                if isinstance(result, str):
                    result = {'id': result}
                options = tuple(self.expand(data['ingredient']))
                output, amount = result['id'], result.get('count', 1)
                if not options or type(amount) is not int or not 1 <= amount <= 64:
                    raise ValueError('Invalid ordinary furnace recipe: ' + name)
                ticks = data.get('cookingtime', 200)
                if type(ticks) is not int or ticks <= 0:
                    raise ValueError('Invalid furnace cooking time: ' + name)
                key = 'smelting/' + name.removeprefix('data/minecraft/recipe/').removesuffix('.json')
                self.recipes[output].append(Recipe(key, output, amount, 1, ((1, options),), 'minecraft:smelting'))
                self.smelting[key] = {'cooking_ticks_per_recipe': ticks, 'device': 'minecraft:furnace'}


def verified_stock(projection, audit):
    """Preserve uncertainty rather than treating old or missing stock as fresh zero."""
    if not isinstance(audit.get('sources'), list):
        raise ValueError('Stock audit must contain explicit sources, not a historical aggregate')
    cutoff = projection.get('observed_at')
    if type(cutoff) is not int or cutoff <= 0:
        raise ValueError('Projection comparison needs observed_at to order material changes')
    pools = {'carried': Counter(), 'depot': Counter()}
    unknown, excluded, seen, locations = [], [], set(), set()
    carried_source = None
    observed_sources = 0
    if audit.get('complete') is not True:
        unknown.append({'source': 'stock_audit', 'reason': 'Source coverage is incomplete or unknown'})
    for row in audit['sources']:
        key, kind = row.get('key'), row.get('kind')
        if not isinstance(key, str) or not key or key in seen:
            raise ValueError('Each stock source needs a distinct nonempty key')
        seen.add(key)
        counts = quantities(row.get('counts', {}))
        if kind == 'installed':
            excluded.append({'source': key, 'reason': 'Placed equipment is not carried crafting input', 'counts': dict(counts)})
            continue
        if kind == 'historical':
            unknown.append({'source': key, 'reason': 'Historical record has not been freshly inspected'})
            continue
        if kind not in pools:
            raise ValueError('Unsupported stock source kind: ' + str(kind))
        if not isinstance(row.get('counts'), dict):
            raise ValueError('A verified source needs an explicit counts object')
        if kind == 'carried':
            if carried_source is not None:
                raise ValueError('Use one current backpack snapshot, not several observations of the same inventory')
            carried_source = key
        if kind == 'depot' and 'position' in row:
            position = row['position']
            if not isinstance(position, list) or len(position) != 3 or any(type(v) is not int for v in position):
                raise ValueError('Depot position must contain three integer coordinates')
            identity = (row.get('server'), row.get('dimension'), *position)
            if identity in locations:
                raise ValueError('The same depot cannot be counted twice')
            locations.add(identity)
        mismatch = any(projection.get(field) and row.get(field) != projection[field]
                       for field in ('server', 'dimension'))
        observed = row.get('observed_at')
        if mismatch or type(observed) is not int or observed < cutoff:
            unknown.append({'source': key, 'reason': 'Source scope or observation predates the projection comparison'})
            continue
        if row.get('complete') is not True:
            unknown.append({'source': key, 'reason': 'Only a partial stock count is available'})
        pools[kind].update(counts)
        observed_sources += 1
    if not observed_sources:
        unknown.append({'source': 'stock_audit', 'reason': 'No material source has been inspected'})
    return pools, unknown, excluded


def plan(projection, stock_audit, catalog):
    if not isinstance(projection.get('replacement_items'), dict):
        raise ValueError('Projection comparison must provide replacement_items')
    if projection.get('loaded_chunks_verified') is not True:
        raise ValueError('Projection comparison must verify the loaded build region')
    targets = quantities(projection['replacement_items'])
    pools, unknown, excluded = verified_stock(projection, stock_audit)
    available = pools['carried'] + pools['depot']
    raw = MaterialPlanner(catalog).plan(targets, available)
    crafting, smelting = [], []
    for step in raw['steps']:
        if step['kind'] != 'craft':
            continue
        processing = catalog.smelting.get(step['recipe_id'])
        if processing:
            smelting.append({**step, 'kind': 'smelt', **processing,
                             'total_cooking_ticks': step['rounds'] * processing['cooking_ticks_per_recipe']})
        else:
            crafting.append(step)
    cooking_ticks = sum(step['total_cooking_ticks'] for step in smelting)
    smelt_totals, craft_totals = Counter(), Counter()
    for step in smelting:
        smelt_totals[step['item']] += step['produced']
    for step in crafting:
        craft_totals[step['item']] += step['produced']
    # Parallel furnaces and interrupted burns may use more than this ideal lower
    # bound. It is a fuel planning hint, never a receipt of loaded furnace fuel.
    coal_lower_bound = (cooking_ticks + 1599) // 1600
    return {
        'schema': 1, 'planning_only': True, 'executable': False, 'placement_key': projection.get('placement_key'),
        'projection_observed_at': projection['observed_at'], 'building_remaining': dict(targets),
        'quantity_status': 'unknown' if unknown else 'verified_audit_snapshot',
        'deficit_basis': 'upper_bound_from_verified_stock' if unknown else 'net_of_verified_stock',
        'unknown_sources': unknown, 'excluded_sources': excluded,
        'carried_stock': dict(pools['carried']), 'depot_stock_requires_withdrawal': dict(pools['depot']),
        'acquire': raw['missing_supplies'], 'smelt': smelting, 'craft': crafting,
        'smelt_totals': dict(smelt_totals), 'craft_totals': dict(craft_totals),
        'ordered_processing': [step if step['recipe_id'] not in catalog.smelting
                               else {**step, 'kind': 'smelt', **catalog.smelting[step['recipe_id']]}
                               for step in raw['steps'] if step['kind'] == 'craft'],
        'fuel': {'coal_equivalent_lower_bound': coal_lower_bound,
                 'coal_in_verified_stock': available.get('minecraft:coal', 0),
                 'exact_required_fuel': None,
                 'reason': 'Choose a furnace distribution and inspect retained fuel before loading'},
        'surplus': raw['surplus'], 'source_jar': str(catalog.jar),
        'requires_fresh_inventory_before_execution': True,
        'notes': ['Targets are remaining projection items, including recipe ingredients; no fixed historic quota is reused.',
                  'Installed furnace-bank blocks are excluded unless separately recovered and freshly audited as carried or depot stock.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jar', type=Path, required=True)
    parser.add_argument('--projection', type=Path, required=True)
    parser.add_argument('--stock', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = plan(json.loads(args.projection.read_text()), json.loads(args.stock.read_text()), ProcessingCatalog(args.jar))
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    print(serialized)


if __name__ == '__main__':
    main()
