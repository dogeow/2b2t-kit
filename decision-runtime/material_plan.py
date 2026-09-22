"""Deterministic, stock-aware crafting dependencies from the installed vanilla JAR.

Planning is read-only. Missing supplies are explicit prerequisites, never invented stock.
The executor must recheck live inventory and the safety interlock before every action.
"""
from collections import Counter
from dataclasses import dataclass, field
from copy import deepcopy
from pathlib import Path
import argparse
import json
import math

from recipe_catalog import RecipeCatalog


class Cycle(Exception):
    pass


class PlanningLimit(RuntimeError):
    pass


def quantities(value):
    result = Counter()
    for item, count in value.items():
        if not isinstance(item, str) or not item.startswith('minecraft:'):
            raise ValueError('Expected a vanilla item ID')
        if isinstance(count, bool) or not isinstance(count, int) or count < 0 or count > 100000:
            raise ValueError('Invalid material count')
        if count:
            result[item] += count
    return result


@dataclass
class State:
    stock: Counter
    missing: Counter = field(default_factory=Counter)
    steps: list = field(default_factory=list)

    def copy(self):
        return State(self.stock.copy(), self.missing.copy(), deepcopy(self.steps))


class MaterialPlanner:
    def __init__(self, catalog, max_expansions=20000, acquisition_items=None):
        self.catalog = catalog
        self.max_expansions = max_expansions
        self.expansions = 0
        self.acquisition_items = set(acquisition_items if acquisition_items is not None else (
            'minecraft:leather', 'minecraft:white_wool', 'minecraft:coal', 'minecraft:iron_ingot',
            'minecraft:gold_ingot', 'minecraft:diamond', 'minecraft:lapis_lazuli', 'minecraft:redstone',
            'minecraft:emerald', 'minecraft:bone_meal'))

    def _candidates(self, item, stock):
        # A batch may need hundreds of planks. A few loose birch planks must not
        # force every barrel to use birch when oak logs can supply the whole batch.
        potential = stock.copy()
        for recipes in self.catalog.recipes.values():
            for recipe in recipes:
                if len(recipe.cells) == 1:
                    _, options = recipe.cells[0]
                    count = sum(stock[option] for option in options if option != recipe.output)
                    potential[recipe.output] = max(potential[recipe.output], stock[recipe.output] + count * recipe.count)
        found = {}
        for selection_stock in (potential, stock):
            for candidate in self.catalog.candidates(item, selection_stock, 3):
                key = (candidate['recipe_id'], tuple((k, tuple(v)) for k,v in sorted(candidate['ingredients'].items())))
                found.setdefault(key, candidate)
        return list(found.values())

    def _need(self, item, count, state, ancestors=()):
        take = min(count, state.stock[item])
        state.stock[item] -= take
        count -= take
        if not count:
            return state
        if item in ancestors:
            raise Cycle(item)
        self.expansions += 1
        if self.expansions > self.max_expansions:
            raise PlanningLimit('Recipe search limit reached; no executable plan produced')
        if len(ancestors) >= 16:
            raise Cycle(item)
        try:
            candidates = self._candidates(item, state.stock)
        except ValueError:
            candidates = []
        choices = []
        cyclic = []
        for spec in candidates:
            if spec['missing_for_one'].get('unsupported_same_item_conversion'):
                continue
            rounds = math.ceil(count / spec['produces'])
            trial = state.copy()
            ingredients = {key: rounds * len(slots) for key, slots in spec['ingredients'].items()}
            try:
                for ingredient, required in sorted(ingredients.items()):
                    trial = self._need(ingredient, required, trial, ancestors + (item,))
            except Cycle as cycle:
                cyclic.append(cycle.args[0])
                continue
            produced = rounds * spec['produces']
            trial.stock[item] += produced - count
            trial.steps.append({
                'kind': 'craft', 'item': item, 'recipe_id': spec['recipe_id'],
                'rounds': rounds, 'produced': produced, 'ingredients': ingredients,
                'grid': spec['ingredients'], 'produces_per_recipe': spec['produces'],
                'width': spec['width'],
            })
            # Prefer recipes that consume actual stock over recipes needing new resources.
            score = (sum(trial.missing.values()) - sum(state.missing.values()),
                     len(trial.steps) - len(state.steps), sum(ingredients.values()), spec['recipe_id'])
            choices.append((score, trial))
            if score[0] == 0:
                break
        if item in self.acquisition_items:
            trial = state.copy()
            trial.missing[item] += count
            trial.steps.append({'kind':'acquire', 'item':item, 'count':count,
                                'reason':'Base supply; compare with verified conversion recipes'})
            choices.append(((count, 1, count, 'acquire'), trial))
        if choices:
            return min(choices, key=lambda row: row[0])[1]
        if cyclic and item not in cyclic:
            raise Cycle(cyclic[0])
        state.missing[item] += count
        state.steps.append({'kind': 'acquire', 'item': item, 'count': count,
                            'reason': 'No ordinary crafting recipe; obtain or process separately'})
        return state

    def plan(self, targets, stock, keep=None):
        targets, original, keep = quantities(targets), quantities(stock), quantities(keep or {})
        self.expansions = 0
        free = original.copy()
        kept = {item: min(count, free[item]) for item, count in keep.items()}
        free.subtract(kept)
        # Reserve all directly usable target items before expanding any dependencies.
        reserved = {item: min(count, free[item]) for item, count in targets.items()}
        free.subtract(reserved)
        state = State(free)
        for item, count in sorted(targets.items()):
            needed = count - reserved[item]
            if not needed:
                continue
            baseline = state.copy()
            try:
                state = self._need(item, needed, state)
            except Cycle:
                # Do not turn an ingot/block or dye cycle into imaginary raw supplies.
                state = baseline
                take = min(needed, state.stock[item])
                state.stock[item] -= take
                needed -= take
                if needed:
                    state.missing[item] += needed
                    state.steps.append({'kind': 'acquire', 'item': item, 'count': needed,
                                        'reason': 'Available recipes form a conversion cycle'})
            state.steps.append({'kind': 'reserve', 'item': item, 'count': count})
        return {
            'schema': 1, 'source_jar': str(self.catalog.jar), 'planning_only': True,
            'targets': dict(targets), 'input_stock': dict(original), 'keep': dict(keep),
            'kept': kept, 'reserved_finished_items': reserved,
            'steps': state.steps, 'missing_supplies': dict(+state.missing),
            'surplus': dict(+state.stock), 'search_expansions': self.expansions,
            'requires_fresh_inventory_before_execution': True,
        }


def inventory_counts(snapshot):
    if not isinstance(snapshot.get('inventory'), list):
        raise ValueError('Input must include a timestamped inventory snapshot')
    stock = Counter()
    for entry in snapshot['inventory']:
        if entry.get('slot', 99) < 36 and entry.get('count', 0) > 0:
            stock[entry['item']] += entry['count']
    return stock


def ledger_counts(ledger):
    """Only explicitly selected, distinct permanent depots enter a historical estimate.

    A moved shulker can leave several position records; never sum those as separate stock.
    """
    result = Counter()
    seen = set()
    for source in ledger['sources']:
        key = source['key']
        if key in seen:
            raise ValueError('Duplicate stock source')
        seen.add(key)
        if source['kind'] == 'warehouse_record':
            if source.get('block_id') not in ('minecraft:chest', 'minecraft:trapped_chest', 'minecraft:barrel'):
                raise ValueError('Portable or shared container records require live inspection')
        elif source['kind'] != 'inventory_record':
            raise ValueError('Unsupported stock source')
        if not isinstance(source.get('observed_at'), int):
            raise ValueError('Source observation time required')
        result.update(quantities(source['stock']))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jar', type=Path, required=True)
    p.add_argument('--audit', type=Path, required=True)
    inputs = p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--inventory', type=Path)
    inputs.add_argument('--stock-ledger', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    audit = json.loads(args.audit.read_text())
    snapshot = json.loads(args.inventory.read_text()) if args.inventory else None
    ledger = json.loads(args.stock_ledger.read_text()) if args.stock_ledger else None
    stock = inventory_counts(snapshot) if snapshot is not None else ledger_counts(ledger)
    plan = MaterialPlanner(RecipeCatalog(args.jar)).plan(audit['replacement_items'], stock)
    plan['placement_key'] = audit['placement_key']
    if snapshot is not None:
        plan['inventory_observed_at'] = snapshot.get('time')
        plan['inventory_world_session'] = snapshot.get('world_session')
    else:
        plan['stock_sources'] = ledger['sources']
        plan['stock_is_historical_estimate'] = True
        plan['requires_depot_revalidation'] = True
    plan['remaining_world_differences'] = audit['kinds']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    print(json.dumps({'craft_steps': sum(s['kind'] == 'craft' for s in plan['steps']),
                      'missing_supplies': plan['missing_supplies'],
                      'planning_only': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
