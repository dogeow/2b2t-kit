"""Reuse installed recipes and bounded crafting/fuel dependencies."""
from collections import Counter, defaultdict
import copy

from material_plan import MaterialPlanner, quantities
from recipe_catalog import Recipe

COLORS = ('white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink',
          'gray', 'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black')

# These ordinary drops have actual ROCK_SOURCES/native quarry adapters. Keep
# this planner dependency-free; the regression checks the acquisition contract.
DIRECT_ROCK_DROPS = frozenset('minecraft:'+name for name in (
    'cobblestone', 'cobbled_deepslate', 'andesite', 'diorite', 'granite', 'tuff', 'calcite', 'raw_iron_block'))


class _DirectRockPlanner(MaterialPlanner):
    def _need(self, item, count, state, ancestors=()):
        if item not in DIRECT_ROCK_DROPS:
            return super()._need(item, count, state, ancestors)
        before = state.copy()
        converted = super()._need(item, count, state, ancestors)
        if not any(amount > before.missing[material]
                   for material, amount in converted.missing.items()):
            # A real stock-only conversion remains useful. Only avoid collecting
            # new recipe ingredients for an already directly obtainable rock.
            return converted
        held = min(count, before.stock[item])
        before.stock[item] -= held
        missing = count - held
        before.missing[item] += missing
        before.steps.append({'kind':'acquire', 'item':item, 'count':missing,
                             'reason':'Existing natural-rock adapter; retain stock rather than gather synthesis inputs'})
        return before


def _baked_wood_plan(catalog, targets, stock, hint, factory):
    """Prepare verified carried wood for ordinary baked potatoes only.

    Fuel keep protects later wood crafting, not potatoes used as input. Seed
    reservation remains caller-managed; no source_keep field is supported by
    the generic material worker. This plan adds no default seed reservation.
    """
    result = factory(catalog, targets, stock, hint)
    baked, potato = 'minecraft:baked_potato', 'minecraft:potato'
    if (not targets.get(baked) or stock.get('minecraft:coal', 0)
            or stock.get('minecraft:charcoal', 0)):
        return result
    cooking = next((step for step in result['steps'] if step.get('item') == baked
                    and step.get('recipe_id') in getattr(catalog, 'smelting', {})
                    and step.get('ingredients') == {potato: step.get('produced')}), None)
    if cooking is None or stock.get(potato, 0) < cooking['produced']:
        return result
    from smelting_fuel import FuelCatalog
    fuel = FuelCatalog(catalog.jar)
    if not fuel.evidence.get('extra_fuels_verified'):
        return result
    protected = {item: min(count, stock.get(item, 0)) for item, count in targets.items() if item != baked}
    free = Counter(stock); free.subtract(protected); free = dict(+free)
    candidates = []
    for output, rows in catalog.recipes.items():
        if not output.endswith('_planks') or output not in fuel.wood:
            continue
        for recipe in rows:
            if recipe.count != 4 or len(recipe.cells) != 1:
                continue
            raw = [item for item in recipe.cells[0][1] if item in fuel.wood and free.get(item, 0)]
            if not free.get(output, 0) and not raw:
                continue
            source = min(raw, key=lambda item: (-free[item], item)) if raw else None
            candidates.append((output, source, recipe))
    if not candidates:
        return result
    plank, raw, recipe = min(candidates, key=lambda row:
        (-free.get(row[0], 0), -free.get(row[1], 0), row[0], row[1] or ''))
    ticks = catalog.smelting[cooking['recipe_id']]['cooking_ticks_per_recipe']
    # The planner has no profile. Prepare a finite upper bound for the adapter's
    # supported 1..16 ordinary furnaces, then its actual selector loads only the
    # verified live bank's demand. Unused crafted planks remain real inventory.
    amount = min(cooking['produced'], 16 * min(64, 102400 // ticks))
    burn = fuel.durations[plank]
    fuel_count = max(sum((n*ticks + burn-1)//burn for n in
        [amount//size + (index < amount%size) for index in range(size)]) for size in range(1, 17))
    index = result['steps'].index(cooking)
    keep = targets.get(plank, 0) + sum(step.get('ingredients', {}).get(plank, 0)
                                      for step in result['steps'][index+1:])
    need = max(0, fuel_count + keep - protected.get(plank, 0))
    selected = copy.copy(catalog)
    selected.recipes = defaultdict(list, {item: list(rows) for item, rows in catalog.recipes.items()})
    if raw is not None:
        selected.recipes[plank] = [Recipe(recipe.id, recipe.output, recipe.count, recipe.width,
                                        ((recipe.cells[0][0], (raw,)),), recipe.kind)]
    prefix = factory(selected, {plank: need}, free, {}) if need else None
    prefix_ready = not prefix or not prefix['missing_supplies']
    if not prefix_ready:
        minimum = (amount*ticks + burn-1)//burn + keep - protected.get(plank, 0)
        capacity = free.get(plank, 0) + (4*free.get(raw, 0) if raw is not None else 0)
        if capacity < minimum:
            return result  # Even one furnace cannot fit without spending protected inputs.
        # A smaller actual bank may fit these carried planks already. Let its
        # real fuel selector report the exact shortage, without forecasting new wood.
        prefix = None
    if prefix:
        from .torch_planning import _after
        after = _after(prefix, stock)
        result = factory(catalog, targets, after, hint)
        result['steps'] = [step for step in prefix['steps'] if step['kind'] != 'reserve'] + result['steps']
        result['input_stock'] = dict(stock)
        result['reserved_finished_items'] = {item: min(count, stock.get(item, 0)) for item, count in targets.items()}
    for index, step in enumerate(result['steps']):
        if step.get('item') == baked and step.get('recipe_id') in catalog.smelting:
            step['fuel_allow_items'] = [plank]
            step['fuel_keep'] = {plank: targets.get(plank, 0) + sum(
                later.get('ingredients', {}).get(plank, 0) for later in result['steps'][index+1:])}
    result['fuel_preparation'] = {'item': plank, 'from_carried_stock_only': True,
                                  'maximum_furnaces': 16, 'stock_prefix_ready': prefix_ready,
                                  'source_reserve_supported': False}
    return result


def plan(catalog, targets, stock, warehouse_hint=None):
    expanded = copy.copy(catalog)
    expanded.recipes = defaultdict(list, {item: list(recipes) for item, recipes in catalog.recipes.items()})
    # Mining returns raw metals. Do not ask acquisition to find finished ingots
    # or silk-touch ore blocks merely because those paths have one fewer step.
    processed = set()
    for metal in ('iron', 'gold', 'copper'):
        output, raw = 'minecraft:'+metal+'_ingot', 'minecraft:raw_'+metal
        ordinary = [r for r in expanded.recipes.get(output, [])
                    if r.id in getattr(catalog, 'smelting', {}) and len(r.cells)==1 and raw in r.cells[0][1]]
        if ordinary:
            expanded.recipes[output] = ordinary
            processed.add(output)
    hint = quantities(warehouse_hint or {})
    if any(stock.get(item,0) or hint.get(item,0) for item in ('minecraft:bone_block','minecraft:bone_meal')):
        def from_item(output, source):
            recipes = [r for r in expanded.recipes.get(output, []) if len(r.cells)==1 and source in r.cells[0][1]]
            if recipes:
                expanded.recipes[output] = recipes
                processed.add(output)
        from_item('minecraft:white_dye','minecraft:bone_meal')
        if stock.get('minecraft:bone_block',0) or hint.get('minecraft:bone_block',0):
            from_item('minecraft:bone_meal','minecraft:bone_block')
    hardening = {}
    for color in COLORS:
        item = 'minecraft:' + color + '_concrete'
        powder = item + '_powder'
        recipe_id = 'material_job/harden/' + color
        expanded.recipes[item].append(Recipe(recipe_id, item, 1, 1, ((1, (powder,)),), 'hardening'))
        hardening[recipe_id] = powder
    acquisition = {'minecraft:leather','minecraft:white_wool','minecraft:coal','minecraft:diamond',
                   'minecraft:lapis_lazuli','minecraft:redstone','minecraft:emerald','minecraft:bone_meal',
                   # These are actual mining drops, not the reverse packing or
                   # Silk-Touch ore recipes. A leaf prerequisite does not imply
                   # a collection adapter exists; unsupported acquisition still
                   # stops at the backend. Verified stock conversions remain usable.
                   'minecraft:raw_iron','minecraft:raw_copper','minecraft:raw_gold','minecraft:quartz',
                   # Prefer a bounded Silk-Touch surface harvest over turning
                   # 120 newly mined snowballs into 58 requested snow layers.
                   'minecraft:snow'} | DIRECT_ROCK_DROPS
    acquisition -= processed
    if stock.get('minecraft:bone_block',0) or hint.get('minecraft:bone_block',0):
        # The reverse nine-meal packing recipe must not turn this known depot
        # source into a dependency cycle or imaginary directly gathered meal.
        acquisition.add('minecraft:bone_block')
    from .torch_planning import plan as plan_torch_prefix
    def ordinary(current_catalog, current_targets, current_stock, current_hint):
        return plan_torch_prefix(current_catalog, current_targets, current_stock, current_hint,
            lambda selected_catalog, selected_targets, selected_stock:
                _DirectRockPlanner(selected_catalog, acquisition_items=acquisition).plan(selected_targets, selected_stock))
    result = _baked_wood_plan(expanded, targets, quantities(stock), hint, ordinary)
    for step in result['steps']:
        if step['kind'] != 'craft':
            continue
        recipe = step['recipe_id']
        if recipe in hardening:
            step.update(kind='harden', source=hardening[recipe], output=step['item'])
        elif recipe in getattr(catalog, 'smelting', {}):
            if len(step['ingredients']) != 1:
                raise ValueError('Ordinary smelting needs exactly one input material')
            step.update(kind='smelt', source=next(iter(step['ingredients'])), output=step['item'],
                        **catalog.smelting[recipe])
    return result
