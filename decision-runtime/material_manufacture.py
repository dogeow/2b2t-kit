"""Execute freshly planned crafting dependencies under an existing MaterialClient lease."""
from collections import Counter
import json
import time

import craft_recipe
import stack_recipe
from material_plan import MaterialPlanner, inventory_counts
from safety_interlock import require_unlocked



class _InventoryCatalog:
    """Let the existing dependency planner select native 2x2 layouts only."""
    def __init__(self, catalog):
        self.source, self.jar = catalog, catalog.jar
        self.recipes = {item:[recipe for recipe in recipes if recipe.width <= 2]
                        for item, recipes in catalog.recipes.items()}

    def candidates(self, item, stock, menu_width=None):
        return self.source.candidates(item, stock, 2)


def inventory_plan(catalog, targets, stock, keep=None):
    plan = MaterialPlanner(_InventoryCatalog(catalog)).plan(targets, stock, keep)
    return None if plan['missing_supplies'] else plan


def _inventory_state(state, menu_id=None, *, empty=False):
    menu = state.get('menu', {})
    if (state.get('screen') or menu.get('type') != 'InventoryMenu' or menu.get('id') != 0
            or menu_id is not None and menu.get('id') != menu_id
            or len(menu.get('slots', [])) < 45
            or state.get('inventory_cursor_precondition_protocol', 0) < 1
            or state.get('inventory_isolation', {}).get('supported') is not True
            or state.get('inventory_isolation', {}).get('active') is not True):
        raise RuntimeError('Owned isolated inventory menu changed; player UI is preserved')
    if empty and (menu.get('cursor', {}).get('count') != 0
                  or any(menu['slots'][i].get('count') != 0 for i in range(1, 5))):
        raise RuntimeError('Inventory crafting grid or cursor is already occupied; preserve player items')
    return state


def _inventory_output_room(slots, spec):
    # Empty ItemStacks report max_stack=1.  Only the explicit stack-recipe
    # allowlist is known to have ordinary 64-item outputs.  Other recipes
    # conservatively reserve no more than one recipe result per empty slot.
    empty_limit = 64 if stack_recipe.supported(spec) else spec['produces']
    return sum(
        empty_limit if not row['count'] else
        max(0, row.get('max_stack', empty_limit) - row['count'])
        if row['item'] == spec['output'] else 0
        for row in slots)


def _inventory_batch(state, spec, target_total, max_rounds=64):
    """Plan one server-shift-click batch using only ordinary inventory slots.

    The 2x2 grid consumes one item from every named cell per recipe round.  A
    shift-click on the result is useful only when we can first prove that every
    cell can receive the same number of rounds and that the resulting items fit
    after those inputs leave the backpack.  Unknown recipes retain the historic
    one-round behavior; ``stack_recipe`` is the explicit no-container-remainder
    allowlist used by the already verified workbench batch path.
    """
    menu = state['menu']
    current = inventory_counts(state)[spec['output']]
    remaining = target_total - current
    if remaining <= 0:
        return {'rounds': 0, 'produced': 0}
    produces = spec['produces']
    if (isinstance(produces, bool) or not isinstance(produces, int)
            or not 1 <= produces <= 64 or remaining % produces):
        raise RuntimeError('Inventory target is not an exact number of recipe rounds')
    cells = [cell for positions in spec['ingredients'].values() for cell in positions]
    desired = min(max_rounds, remaining // produces)
    if not stack_recipe.supported(spec):
        desired = min(desired, 1)
    for rounds in range(desired, 0, -1):
        slots = [dict(row) for row in menu['slots'][9:45]]
        actions = []
        possible = True
        for item, positions in spec['ingredients'].items():
            for cell in positions:
                sources = [row for row in slots if row['item'] == item and row['count'] >= rounds]
                if not sources:
                    possible = False
                    break
                source = min(sources, key=lambda row: (stack_recipe.split_cost(row['count'], rounds),
                                                       row['slot']))
                actions.append({'source': source['slot'], 'source_count': source['count'],
                                'item': item, 'cell': cell, 'count': rounds})
                source['count'] -= rounds
                if not source['count']:
                    source['item'] = 'minecraft:air'
            if not possible:
                break
        if not possible:
            continue
        room = _inventory_output_room(slots, spec)
        if room >= rounds * produces:
            return {'rounds': rounds, 'produced': rounds * produces,
                    'actions': actions}
    raise craft_recipe.InventoryCapacity('Inventory recipe batch has no verified input layout and output space')


def _inventory_execute(client, spec, target_total):
    """Craft through owned menu-0 cells without opening or closing any UI."""
    from kit_runtime.inventory import InventorySession
    if spec.get('width') != 2:
        raise RuntimeError('Inventory manufacturing requires a 2x2 recipe')
    cells = [cell for slots in spec['ingredients'].values() for cell in slots]
    if not cells or len(set(cells)) != len(cells) or any(type(cell) is not int or not 1 <= cell <= 4 for cell in cells):
        raise RuntimeError('Invalid inventory recipe cells')

    class OwnedInventory:
        def status(self):
            state=client.status()
            require_unlocked(client.root,state)
            return _inventory_state(state)

        def checked(self, op, **params):
            self.status()  # A newly opened player UI is never closed or clicked.
            return _inventory_state(client.checked(op, **params))

    owned = OwnedInventory()
    session = InventorySession(owned)
    while True:
        before = _inventory_state(owned.status(), empty=True)
        initial = inventory_counts(before)
        if initial[spec['output']] >= target_total:
            client.owned_inventory_crafting = None
            return before
        batch = _inventory_batch(before, spec, target_total)
        rounds, produced = batch['rounds'], batch['produced']
        # The empty preflight above proves any subsequent menu-0 cursor/grid
        # contents belong to this task.  Keep the marker on exceptions so the
        # guarded finish path can return them without claiming arbitrary state.
        client.owned_inventory_crafting = {
            'menu_id': 0,
            'world_session': before.get('world_session', getattr(client, 'world', None)),
            'task_session': getattr(client, 'task', None),
        }
        state = before
        for action in batch['actions']:
            source = state['menu']['slots'][action['source']]
            # Same-item pickups may legitimately increase this exact source
            # after planning.  A decrease or identity change invalidates the
            # capacity proof; never silently substitute a different stack.
            if (source['item'] != action['item']
                    or source['count'] < action['source_count']):
                raise RuntimeError('Planned inventory recipe source changed; no duplicate craft')
            state = session.place_cell(state, source, action['cell'], action['count'])
            state = session.wait_grid(state, 0, action['item'],
                                      [action['cell']], action['count'])
        state = session.wait_recipe(state, spec['output'])
        if state['menu']['slots'][0]['count'] != spec['produces']:
            raise RuntimeError('Inventory recipe output quantity differs from the catalog')
        # Refresh the round balance after all input pickups are settled. Nearby
        # drops may legitimately add the same ingredient while a full stack is
        # on the cursor; those items are preserved and must not make the already
        # acknowledged click look like duplicate consumption.
        pre_output = inventory_counts(state)
        ingredient_totals = {
            item: pre_output[item] + sum(state['menu']['slots'][cell]['count'] for cell in slots)
            for item, slots in spec['ingredients'].items()
        }
        if _inventory_output_room(state['menu']['slots'][9:45], spec) < produced:
            # The owned grid remains recoverable by the guarded material-task
            # finish path.  No output click has been sent and no alternative
            # source or smaller batch is guessed from this changed inventory.
            raise RuntimeError('Inventory output capacity changed after batch placement; owned grid requires recovery')
        state = session.click(state, 0, 'quick_move')
        state = session._wait(
            state, 0,
            lambda menu: sum(row['count'] for row in menu['slots'][9:45]
                             if row['item'] == spec['output'])
                         == pre_output[spec['output']] + produced
                         and menu['cursor']['count'] == 0
                         and (all(not menu['slots'][cell]['count'] for cell in cells)
                              if rounds > 1 else
                              all(not menu['slots'][cell]['count']
                                  or menu['slots'][cell]['item'] not in spec['ingredients']
                                  for cell in cells)),
            'inventory_output', confirmations=2, interval=.1, fresh=True)
        # These cells were empty before our recipe. Return only confirmed
        # recipe remainders from them, never a preexisting/user-owned grid.
        for cell in cells:
            row = state['menu']['slots'][cell]
            if not row['count']:
                continue
            state = session.click(state, cell, 'quick_move')
            state = session._wait(state, 0, lambda menu: menu['slots'][cell]['count'] == 0,
                                  'owned_inventory_grid_return', confirmations=2,
                                  interval=.1, fresh=True)
        final = _inventory_state(owned.status(), empty=True)
        stock = inventory_counts(final)
        if (stock[spec['output']] - pre_output[spec['output']] != produced
                or any(ingredient_totals[item] - stock[item] != rounds * len(slots)
                       for item, slots in spec['ingredients'].items())):
            raise RuntimeError('Inventory recipe balances differ; do not repeat the operation')


def manufacture(client, catalog, targets, keep=None, allow_partial=False):
    # A historical offline plan is never accepted as an execution request.
    snapshot = client.status()
    require_unlocked(client.root, snapshot)
    inventory_mode = snapshot.get('menu', {}).get('type') == 'InventoryMenu'
    if inventory_mode:
        _inventory_state(snapshot, empty=True)
        plan = inventory_plan(catalog, targets, inventory_counts(snapshot), keep)
        if plan is None:
            raise RuntimeError('Current inventory cannot completely manufacture these targets in 2x2')
    else:
        if snapshot.get('menu', {}).get('type') != 'CraftingMenu':
            raise RuntimeError('Open the verified workbench before manufacturing')
        plan = MaterialPlanner(catalog).plan(targets, inventory_counts(snapshot), keep)
    stamp = str(int(time.time() * 1000))
    (client.out / ('material-plan-' + stamp + '.json')).write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    reserved = Counter(plan['reserved_finished_items'])
    results = []
    for step in plan['steps']:
        snapshot = client.status()
        require_unlocked(client.root, snapshot)
        if step['kind'] == 'acquire':
            continue
        stock = inventory_counts(snapshot)
        if step['kind'] == 'reserve':
            reserved[step['item']] = min(step['count'], max(0, stock[step['item']] - plan['kept'].get(step['item'], 0)))
            continue
        missing = {item: amount - max(0, stock[item] - reserved[item] - plan['kept'].get(item, 0))
                   for item, amount in step['ingredients'].items()
                   if amount > max(0, stock[item] - reserved[item] - plan['kept'].get(item, 0))}
        produced=step['produced']
        if missing and allow_partial:
            rounds=min(step['rounds'],*(max(0,stock[item]-reserved[item]-plan['kept'].get(item,0))//len(slots) for item,slots in step['grid'].items()))
            if rounds>0:produced=rounds*step['produces_per_recipe']
            else:
                results.append({'item':step['item'],'state':'waiting_for_supplies','missing':missing});continue
        elif missing:
            results.append({'item': step['item'], 'state': 'waiting_for_supplies', 'missing': missing})
            continue
        if snapshot.get('menu', {}).get('type') != ('InventoryMenu' if inventory_mode else 'CraftingMenu'):
            raise RuntimeError('Crafting menu changed; manufacturing stopped')
        spec = {'recipe_id': step['recipe_id'], 'output': step['item'],
                'produces': step['produces_per_recipe'], 'width': step['width'],
                'ingredients': step['grid'], 'missing_for_one': {}}
        try:
            executor=_inventory_execute if inventory_mode else stack_recipe.execute if stack_recipe.supported(spec) else craft_recipe.execute
            after = executor(client, spec, stock[step['item']] + produced)
        except craft_recipe.InventoryCapacity:
            results.append({'item':step['item'],'state':'waiting_for_inventory_space'})
            continue
        except Exception as error:
            if inventory_mode:
                failure = {'schema': 1, 'recipe': spec, 'target_total': stock[step['item']] + produced,
                           'error_type': type(error).__name__, 'detail': str(error),
                           'owned_inventory_crafting': getattr(client, 'owned_inventory_crafting', None)}
                try:
                    observed = client.status(); menu = observed.get('menu', {})
                    failure['observed'] = {
                        'time': observed.get('time'), 'world_session': observed.get('world_session'),
                        'control_revision': observed.get('control_revision'),
                        'menu_id': menu.get('id'), 'menu_type': menu.get('type'),
                        'cursor': menu.get('cursor'), 'grid': menu.get('slots', [])[:5],
                        'inventory': observed.get('inventory', []),
                    }
                except Exception as observation_error:
                    failure['observation_error'] = str(observation_error)
                try:
                    (client.out/('inventory-craft-failure-'+stamp+'.json')).write_text(
                        json.dumps(failure, ensure_ascii=False, indent=2))
                except OSError:
                    pass
            raise
        gained = inventory_counts(after)[step['item']] - stock[step['item']]
        if gained != produced:
            raise RuntimeError('Craft output differs from the fresh material plan')
        results.append({'item': step['item'], 'state': 'crafted' if produced==step['produced'] else 'crafted_partial', 'produced': gained})
        (client.out/('manufacture-progress-'+stamp+'.json')).write_text(json.dumps({'steps':results,'complete':False,'inventory':after.get('inventory',[]),'observed_at':after.get('time')},ensure_ascii=False,indent=2))
    final = client.status()
    stock = inventory_counts(final)
    remaining = {item: n - max(0, stock[item] - plan['kept'].get(item, 0))
                 for item, n in targets.items() if n > max(0, stock[item] - plan['kept'].get(item, 0))}
    result = {'steps': results, 'remaining_targets': remaining, 'inventory_observed_at': final.get('time'),
              'complete': not remaining}
    (client.out / ('manufacture-' + stamp + '.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
