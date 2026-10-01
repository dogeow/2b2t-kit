"""Pure, JAR-verified ready-first torch dependencies; no inventory mutations.

Existing coal/charcoal and craftable sticks are spent in confirmed small plans
before the remainder asks for new supplies. Warehouse hints select a route only;
they never become carried stock. The generic MaterialJob still owns receipts,
fresh replanning, fuel acquisition, pause and unknown-action recovery.
"""
from collections import Counter, defaultdict
import copy

from material_plan import quantities
from recipe_catalog import Recipe

TORCH, STICK = 'minecraft:torch', 'minecraft:stick'
COAL, CHARCOAL = 'minecraft:coal', 'minecraft:charcoal'


def _torch_recipes(catalog):
    result = []
    for recipe in catalog.recipes.get(TORCH, []):
        cells = recipe.cells
        if (recipe.count == 4 and len(cells) == 2
                and sum(set(options) == {STICK} for _, options in cells) == 1
                and sum(set(options) == {COAL, CHARCOAL} for _, options in cells) == 1):
            result.append(recipe)
    return result


def _charcoal_recipes(catalog):
    return [r for r in catalog.recipes.get(CHARCOAL, [])
            if r.id in getattr(catalog, 'smelting', {}) and r.count == 1
            and len(r.cells) == 1 and CHARCOAL not in r.cells[0][1]]


def _with_known_charcoal(catalog, stock, hint):
    """Use the exact installed charcoal recipe when actual/known wood exists."""
    burns = _charcoal_recipes(catalog)
    options = {item for r in burns for _, names in r.cells for item in names}
    known = [item for item in options if stock.get(item, 0) or hint.get(item, 0)]
    if not known:
        return catalog
    raw = min(known, key=lambda item: (not bool(stock.get(item, 0)),
                                     -stock.get(item, 0), -hint.get(item, 0), item))
    selected = copy.copy(catalog)
    selected.recipes = defaultdict(list, {item: list(rows) for item, rows in catalog.recipes.items()})
    selected.recipes[TORCH] = [Recipe(r.id, r.output, r.count, r.width,
                                     tuple((cell, (CHARCOAL,) if set(names) == {COAL, CHARCOAL} else names)
                                           for cell, names in r.cells), r.kind)
                              for r in _torch_recipes(catalog)]
    selected.recipes[CHARCOAL] = [Recipe(r.id, r.output, r.count, r.width,
                                       ((r.cells[0][0], (raw,)),), r.kind)
                                for r in burns if raw in r.cells[0][1]]
    return selected


def _after(planned, stock, *, forecast=False):
    actual = Counter(stock)
    for step in planned['steps']:
        if step['kind'] == 'reserve':
            continue
        if forecast and step['kind'] == 'acquire':
            actual[step['item']] += step['count']  # Explicit prerequisite stays in missing_supplies.
            continue
        if step['kind'] != 'craft':
            raise ValueError('Ready torch prefix cannot acquire or smelt speculative inputs')
        for item, amount in step['ingredients'].items():
            if actual[item] < amount:
                raise ValueError('Ready torch prefix overdraws its actual inputs')
            actual[item] -= amount
        actual[step['item']] += step['produced']
    return dict(+actual)


def _pin_fuel(catalog, fuel):
    selected = copy.copy(catalog)
    selected.recipes = defaultdict(list, {item:list(rows) for item,rows in catalog.recipes.items()})
    selected.recipes[TORCH] = [Recipe(r.id,r.output,r.count,r.width,
        tuple((cell,(fuel,) if set(names)=={COAL,CHARCOAL} else names) for cell,names in r.cells),r.kind)
        for r in _torch_recipes(catalog)]
    return selected


def _charcoal_fuel_authorization(catalog, result, protected):
    """Explicit per-action wood fuel, from actual JAR dependencies only.

    Prefer making the source species' planks over burning four times as many
    logs. The real fuel adapter may return a plank prerequisite; the existing
    MaterialJob resolves it without a special CLI/profile parameter.
    """
    for index, step in enumerate(result['steps']):
        if (step.get('item') != CHARCOAL or step.get('recipe_id') not in getattr(catalog,'smelting',{})
                or len(step.get('ingredients',{})) != 1):
            continue
        source = next(iter(step['ingredients']))
        allowed = sorted({r.output for recipes in catalog.recipes.values() for r in recipes
                          if r.output.endswith('_planks') and r.count == 4 and len(r.cells) == 1
                          and source in r.cells[0][1]}) or [source]
        keep = {item:n for item,n in protected.items() if n}
        for later in result['steps'][index+1:]:
            for item, amount in later.get('ingredients',{}).items():
                if item in allowed:
                    keep[item] = keep.get(item,0) + amount
        step['fuel_allow_items'] = allowed
        step['fuel_keep'] = keep


def plan(catalog, targets, stock, warehouse_hint, factory):
    """Return the complete original goal with an executable owned-stock prefix.

    ``factory(catalog, targets, stock)`` is the existing ordinary planner, not
    this helper again. Up to two ready prefixes handle the two real fuel types
    without pretending that coal and charcoal are interchangeable item stacks.
    """
    targets, stock, hint = map(quantities, (targets, stock, warehouse_hint or {}))
    if not targets.get(TORCH) or not _torch_recipes(catalog):
        return factory(catalog, targets, stock)
    original = Counter(stock); current = dict(stock); prefixes = []; prefix_missing = Counter()
    protected = {item: min(count, stock[item]) for item, count in targets.items() if item != TORCH}
    for _ in range(2):
        held = current.get(TORCH, 0)
        if held >= targets[TORCH]:
            break
        free = Counter(current); free.subtract(protected); free = dict(+free)
        rounds = (targets[TORCH] - held + 3) // 4
        low, high, best = 0, rounds, None
        while low < high:
            probe = (low + high + 1) // 2
            total = min(targets[TORCH], held + probe * 4)
            candidate = factory(catalog, {TORCH: total}, free)
            ready = (not candidate['missing_supplies']
                     and all(s['kind'] in ('craft', 'reserve') for s in candidate['steps']))
            if ready:
                low, best = probe, candidate
            else:
                high = probe - 1
        if not low:
            break
        total = min(targets[TORCH], held + low * 4)
        best = factory(catalog, {TORCH: total}, free)
        current = _after(best, current)
        prefixes.extend(s for s in best['steps'] if s['kind'] != 'reserve')
    ready_after = current.get(TORCH,0)
    # Even when sticks are not yet available, the remaining *owned* fuel need
    # not wait for the entire order's coal. Make its stick prerequisites first,
    # retain their explicit acquire steps, then craft that bounded fuel portion.
    for fuel in (COAL,CHARCOAL):
        free = Counter(current); free.subtract(protected); free = dict(+free)
        fuel_count = min(free.get(fuel,0), (targets[TORCH]-current.get(TORCH,0)+3)//4)
        if fuel_count <= 0:
            continue
        total = min(targets[TORCH],current.get(TORCH,0)+fuel_count*4)
        portion = factory(_pin_fuel(catalog,fuel), {TORCH:total}, free)
        current = _after(portion,current,forecast=True)
        prefixes.extend(s for s in portion['steps'] if s['kind']!='reserve')
        prefix_missing.update(portion['missing_supplies'])
    remainder_catalog = _with_known_charcoal(catalog, current, hint)
    result = factory(remainder_catalog, targets, current)
    if prefixes:
        result['steps'] = prefixes + result['steps']
        result['input_stock'] = dict(original)
        result['reserved_finished_items'] = {item: min(count, original[item]) for item, count in targets.items()}
        result['missing_supplies'] = dict(+(Counter(result['missing_supplies'])+prefix_missing))
        if ready_after > original[TORCH]:
            result['ready_prefix'] = {'item': TORCH, 'actual_carried_before': original[TORCH],
                                      'planned_carried_after': ready_after,
                                      'stock_only_crafting': True, 'not_a_game_receipt': True}
    _charcoal_fuel_authorization(catalog,result,protected)
    return result
