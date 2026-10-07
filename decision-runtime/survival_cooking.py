"""Owned Survival food planning and acknowledged ordinary furnace transactions.

The planner reads the installed recipes/fuel proof. It never acquires materials.
The executor uses the caller's existing Bridge and station, never a material bank
or a second controller. Each ingredient/output intent is durable before clicks.
"""
from collections import Counter
import json
import math
from pathlib import Path
import time
import uuid

from furnace_batches import recipe_balance, wait_loading_balance
from kit_runtime.inventory import InventorySession
from kit_runtime.journal import write_json
from projection_material_plan import ProcessingCatalog
from smelting_fuel import FuelCatalog, COAL, CHARCOAL, select_fuels
from survival_bridge import Paused

RAW = {'minecraft:beef': 'minecraft:cooked_beef',
       'minecraft:porkchop': 'minecraft:cooked_porkchop',
       'minecraft:chicken': 'minecraft:cooked_chicken',
       'minecraft:mutton': 'minecraft:cooked_mutton'}
FOOD = set(RAW.values()) | {'minecraft:apple', 'minecraft:bread',
                           'minecraft:baked_potato', 'minecraft:cooked_salmon',
                           'minecraft:cooked_cod'}
ANIMALS = {'minecraft:cow': 'minecraft:beef', 'minecraft:pig': 'minecraft:porkchop',
           'minecraft:chicken': 'minecraft:chicken', 'minecraft:sheep': 'minecraft:mutton'}
SMALL_FUELS = ('minecraft:leaf_litter', 'minecraft:stick')


def _fuel_stages(catalog, stock, amount, ticks, source, output):
    """Use verified owned stacks first; an item consumed is not a burnt timer."""
    extra = [item for item in SMALL_FUELS if item in catalog.durations]
    allowed = [COAL, CHARCOAL] + sorted(catalog.wood) + extra
    single = select_fuels(catalog, dict(stock), [amount], ticks, source, output, allowed=allowed)
    if single['ready']:
        row = single['entries'][0]
        return [{'fuel_item': row['fuel_item'], 'fuel_count': row['fuel'],
                 'burn_ticks_per_fuel': row['burn_ticks_per_fuel']}]
    # Earlier planks/logs offer a longer preload window. Leaf litter precedes
    # sticks so the current mixed meat can keep two sticks for its next recipe.
    order = [COAL, CHARCOAL] + sorted(i for i in catalog.wood if i.endswith('_planks'))
    order += sorted(i for i in catalog.wood if not i.endswith('_planks')) + extra
    remaining = amount * ticks;stages = []
    for item in order:
        if item in (source, output):continue
        burn = catalog.durations[item]
        count = min(stock[item], 64, math.ceil(remaining / burn))
        if count:
            stages.append({'fuel_item': item, 'fuel_count': count, 'burn_ticks_per_fuel': burn})
            remaining -= count * burn
            if remaining <= 0:return stages
    return None


def counts(state):
    result = Counter()
    rows = state.get('inventory')
    if not isinstance(rows, list) or len(rows) > 128:
        raise ValueError('Cooking requires a bounded actual inventory snapshot')
    for row in rows:
        item, amount = row.get('item'), row.get('count')
        if (not isinstance(item, str) or not item.startswith('minecraft:')
                or type(amount) is not int or not 0 <= amount <= 64):
            raise ValueError('Invalid actual cooking inventory stack')
        if row.get('slot', 0) < 36 and amount and item != 'minecraft:air':
            result[item] += amount
    return result


def cooking_plan(state, actual_recipe_jar, target_food=4):
    """A read-only plan; missing coal is an absolute backpack target.

    Missing raw food may be forecast from one actually observed animal type to
    check fuel *before* hunting. Such input is explicitly marked unowned and the
    plan is never executable until a new snapshot contains the required meat.
    Each different recipe gets its own full fuel allotment. Existing lit time is
    deliberately excluded because the bridge does not expose a verified timer.
    """
    if type(target_food) is not int or not 1 <= target_food <= 64:
        raise ValueError('Cooking food target must be 1..64')
    stock = counts(state)
    cooked = sum(stock[item] for item in FOOD)
    deficit = max(0, target_food - cooked)
    result = {'ready': deficit == 0, 'fuel_ready': True, 'batches': [],
              'coal_requirement': 0, 'missing': {}, 'raw_needed': 0,
              'hunting_source': None, 'target_food': target_food, 'owned_food': cooked}
    if not deficit:
        return result
    if actual_recipe_jar is None:
        raise ValueError('Current installed Minecraft recipe/fuel JAR is required')
    fuel = FuelCatalog(actual_recipe_jar)
    if not fuel.evidence.get('extra_fuels_verified'):
        raise ValueError('Current Minecraft fuel semantics are not verified')
    recipes = ProcessingCatalog(actual_recipe_jar)
    planned = []
    left = deficit
    for source in RAW:
        amount = min(left, stock[source])
        if amount:
            planned.append((source, amount, 0));left -= amount
    result['raw_needed'] = left
    if left:
        # Keep the proposed hunt focused on a known animal type; do not invent
        # a meat source or assume it has already reached the backpack.
        animals = [row for row in state.get('entities', [])
                   if row.get('type') in ANIMALS and row.get('health', 0) > 0]
        if animals:
            position = state.get('pos', [0, 0, 0])
            animal = min(animals, key=lambda row: math.dist(position, row.get('pos', position)))
            source = ANIMALS[animal['type']]
            result['hunting_source'] = source
            previous = next((i for i, row in enumerate(planned) if row[0] == source), None)
            if previous is None:
                planned.append((source, left, left))
            else:
                old_source, amount, _ = planned[previous]
                planned[previous] = (old_source, amount + left, left)
        else:
            result['fuel_ready'] = False
    working = stock.copy()
    missing_coal = 0
    for source, amount, unowned in planned:
        output = RAW[source]
        recipe = next((row for row in recipes.recipes.get(output, [])
                       if row.id in recipes.smelting and row.count == 1
                       and len(row.cells) == 1 and source in row.cells[0][1]), None)
        if recipe is None:
            raise ValueError('Installed ordinary food recipe is missing: ' + source)
        ticks = recipes.smelting[recipe.id]['cooking_ticks_per_recipe']
        working[source] += unowned
        stages = _fuel_stages(fuel, working, amount, ticks, source, output)
        if stages is None:
            # A missing fuel prerequisite is obtained separately. Never turn
            # the food macro into another tree harvesting/crafting workflow.
            need = math.ceil(amount * ticks / fuel.durations[COAL])
            additional = max(0, need - working[COAL])
            missing_coal += additional;working[COAL] += additional
            stages = _fuel_stages(fuel, working, amount, ticks, source, output)
        if stages is None:
            raise ValueError('Food fuel plan cannot be satisfied by a coal prerequisite')
        entry = stages[0]
        result['batches'].append({'recipe_id': recipe.id, 'source': source, 'output': output,
            'amount': amount, 'unowned_input': unowned, 'cooking_ticks': ticks,
            # Legacy fields describe the first actual fuel stack, never an
            # invented coal-equivalent total for different item identities.
            'fuel_item': entry['fuel_item'], 'fuel_count': entry['fuel_count'],
            'burn_ticks_per_fuel': entry['burn_ticks_per_fuel'], 'fuel_stages': stages})
        working[source] -= amount
        for stage in stages:working[stage['fuel_item']] -= stage['fuel_count']
    if missing_coal:
        result['coal_requirement'] = stock[COAL] + missing_coal
        result['missing'][COAL] = result['coal_requirement']
        result['fuel_ready'] = False
    if left:
        result['missing']['raw_food'] = left
    result['ready'] = not result['missing']
    result['evidence'] = fuel.evidence
    return result


def _scope(runner, state):
    return {'world_id': state.get('world_id') or runner.b.world,
            'world_session': state.get('world_session'),
            'trial_id': state.get('trial_identity', {}).get('trial_id'),
            'run_id': state.get('trial_identity', {}).get('run_id')}


def require_no_pending_cooking(runner):
    world = _scope(runner, runner.b.read())['world_id']
    for path in (runner.output / 'cooking').glob('batch-*.json'):
        value = json.loads(path.read_text())
        if (value.get('scope', {}).get('world_id') == world and not value.get('complete')
                and value.get('reconciled') is not True):
            raise Paused('Cooking journal has unfinished native work; inspect it without replay: ' + str(path))


class CookingClient:
    def __init__(self, runner):
        self.runner = runner
        self.root = runner.b.root
        self.out = runner.output
        self.scope = _scope(runner, runner.b.read())

    def status(self):
        state = self.runner.b.read()
        if _scope(self.runner, state) != self.scope:
            raise Paused('Cooking world or run changed; preserve the owned furnace')
        return state

    def checked(self, op, **arguments):
        if op != 'slot_click':
            raise Paused('Cooking SDK only permits scoped ordinary slot clicks')
        self.status()
        return self.runner.b.request(op, **arguments)


def _menu_count(menu, item):
    return sum(row['count'] for row in menu['slots'][3:] if row['item'] == item)


class CookingPartial(Paused):
    """The native result is known but produced fewer items than requested."""


def cook_owned(runner, plan):
    """Execute only an entirely ready plan through this runner's actual furnace."""
    require_no_pending_cooking(runner)
    if not plan.get('ready') or any(row.get('unowned_input') for row in plan['batches']):
        raise Paused('Owned raw food and fuel must cover the complete cooking plan')
    for batch in plan['batches']:
        runner.check()
        stages = batch.get('fuel_stages') or [{key: batch[key] for key in
                    ('fuel_item', 'fuel_count', 'burn_ticks_per_fuel')}]
        fuel_totals = Counter()
        for stage in stages:
            if type(stage['fuel_count']) is not int or not 1 <= stage['fuel_count'] <= 64:
                raise Paused('Cooking fuel stage must fit one actual fuel stack')
            fuel_totals[stage['fuel_item']] += stage['fuel_count']
        held = counts(runner.b.read())
        if held[batch['source']] < batch['amount'] or any(held[item] < count for item, count in fuel_totals.items()):
            raise Paused('Actual food or fuel changed before opening the furnace')
        runner.station('furnace')
        client = CookingClient(runner);state = client.status();menu = state['menu']
        if (menu.get('type') != 'FurnaceMenu' or menu['cursor']['count']
                or len(menu.get('slots', [])) < 39 or any(row['count'] for row in menu['slots'][:3])):
            raise Paused('Furnace or cursor already holds items; preserve the existing contents')
        folder = runner.output / 'cooking';folder.mkdir(exist_ok=True)
        path = folder / ('batch-' + uuid.uuid4().hex + '.json')
        record = {'schema': 1, 'scope': client.scope, 'batch': batch,
                  'menu_id': menu['id'], 'furnace': runner.stations.get('furnace'),
                  'stage': 'prepared', 'pending': None, 'loaded_source': 0,
                  'loaded_fuel': 0, 'complete': False, 'active_fuel_index': None,
                  'fuel_stages': [dict(stage, loaded=0, returned=None, consumed=None,
                                       stage='planned') for stage in stages]}
        session = InventorySession(client)
        def save():write_json(path, record)
        def active_fuel():
            index = record['active_fuel_index']
            return record['fuel_stages'][index] if index is not None else None
        def balance(state):
            stage = active_fuel()
            fuel_item = stage['fuel_item'] if stage else stages[0]['fuel_item']
            loaded = stage['loaded'] if stage else 0
            if state['menu']['id'] != menu['id'] or not recipe_balance(state['menu']['slots'][:3],
                    batch['source'], batch['output'], record['loaded_source'], fuel_item, loaded):
                raise Paused('Owned cooking input/output balance changed; preserve the furnace journal')
        def load_stack(item, target, amount, stage=None):
            loaded = stage['loaded'] if stage is not None else record['loaded_source']
            while loaded < amount:
                current = active_fuel()
                fuel_item = current['fuel_item'] if current else stages[0]['fuel_item']
                fuel_count = current['loaded'] if current else 0
                state = wait_loading_balance(client, client.status(), batch['source'], batch['output'],
                    record['loaded_source'], fuel_count, menu['id'], fuel_item)
                source = max((row for row in state['menu']['slots'][3:]
                              if row['item'] == item and row['count']), key=lambda row: row['count'], default=None)
                if source is None:raise Paused('Owned cooking ingredient disappeared before loading')
                part = min(amount - loaded, source['count']);before = _menu_count(state['menu'], item)
                record.update(stage='input_loading' if target == 0 else 'fuel_loading', pending={
                    'item': item, 'count': part, 'slot': target, 'inventory_before': before,
                    'fuel_stage_index': record['active_fuel_index']})
                if stage is not None:stage['stage'] = 'loading'
                save()
                state = session.place_cell(state, source, target, part, append=True)
                state = session._wait(state, menu['id'],
                    lambda current: not current['cursor']['count'] and _menu_count(current, item) == before - part,
                    'cooking_loading_inventory', confirmations=2, interval=.1, fresh=True)
                source_after = record['loaded_source'] + (part if target == 0 else 0)
                fuel_after = fuel_count + (part if target == 1 else 0)
                wait_loading_balance(client, state, batch['source'], batch['output'],
                                     source_after, fuel_after, menu['id'], fuel_item)
                loaded += part
                if stage is None:record['loaded_source'] = loaded
                else:
                    stage['loaded'] = loaded;stage['stage'] = 'loaded'
                    record['loaded_fuel'] += part
                    stage['acknowledged_at'] = state.get('time')
                record['pending'] = None;save()
        def reconcile_partial():
            """Return only observed owned items after every load was confirmed.

            A known insufficient yield is recoverable. An uncertain click or
            broken conservation proof never enters this cleanup path.
            """
            if record['pending'] is not None or record['stage'] != 'partial_production':
                raise Paused('Uncertain cooking intent cannot be reconciled automatically')
            record.update(stage='partial_reconciling', reconciled_output_count=0,
                          reconciled_raw_count=0, reconciled=False);save()
            while True:
                runner.check();state = client.status();current = active_fuel()
                remaining_recipe = record['loaded_source'] - record['reconciled_output_count'] - record['reconciled_raw_count']
                current_item = current['fuel_item'] if current else stages[0]['fuel_item']
                loaded = current['loaded'] if current else 0
                if state['menu']['id'] != menu['id'] or not recipe_balance(state['menu']['slots'][:3],
                        batch['source'], batch['output'], remaining_recipe, current_item, loaded):
                    raise Paused('Partial cooking conservation changed before recovery')
                if not remaining_recipe:break
                slot = 2 if state['menu']['slots'][2]['count'] else 0
                row = state['menu']['slots'][slot];item = batch['output'] if slot == 2 else batch['source']
                amount = row['count'];before = _menu_count(state['menu'], item)
                key = 'reconciled_output_count' if slot == 2 else 'reconciled_raw_count'
                record['pending'] = {'op': 'recover_known_partial', 'item': item, 'slot': slot,
                                     'count': amount, 'inventory_before': before};save()
                state = session.click(state, slot, 'quick_move')
                session._wait(state, menu['id'], lambda m: not m['cursor']['count']
                    and _menu_count(m, item) == before + amount
                    and recipe_balance(m['slots'][:3], batch['source'], batch['output'],
                                       remaining_recipe - amount, current_item, loaded),
                    'partial_cooking_item_inventory', confirmations=2, interval=.1, fresh=True)
                record[key] += amount;record['pending'] = None;save()
            fuel_left = state['menu']['slots'][1]['count']
            if fuel_left:
                item = current['fuel_item'];before = _menu_count(state['menu'], item)
                record['pending'] = {'op': 'recover_known_partial_fuel', 'item': item,
                                     'slot': 1, 'count': fuel_left, 'inventory_before': before};save()
                state = session.click(state, 1, 'quick_move')
                session._wait(state, menu['id'], lambda m: not m['cursor']['count']
                    and not any(row['count'] for row in m['slots'][:3])
                    and _menu_count(m, item) == before + fuel_left,
                    'partial_cooking_fuel_inventory', confirmations=2, interval=.1, fresh=True)
                record['pending'] = None
            if current is not None:
                current.update(returned=fuel_left, consumed=current['loaded'] - fuel_left)
            # These are real backpack deltas, while complete remains false:
            # this batch did not establish the requested food production goal.
            record.update(stage='partial_reconciled', reconciled=True,
                          reconciled_fuel_returned=fuel_left, complete=False);save()
            runner.b.close()
        save()
        try:
            load_stack(batch['source'], 0, batch['amount'])
            for index, stage in enumerate(record['fuel_stages']):
                # Preload the next item as soon as the prior fuel slot empties,
                # while its last consumed item is still burning. Never wait for
                # all recipe output before an explicitly planned refill.
                previous = active_fuel()
                wait_until = time.monotonic() + (previous['fuel_count'] * previous['burn_ticks_per_fuel'] / 20
                                                 if previous else 0) + 15
                while True:
                    runner.check();state = client.status();balance(state)
                    slots = state['menu']['slots']
                    if not slots[0]['count'] and slots[2]['count'] == batch['amount']:
                        for unused in record['fuel_stages'][index:]:unused['stage'] = 'unneeded_after_verified_output'
                        break
                    if not slots[1]['count']:
                        if previous is not None:
                            previous.update(stage='consumed_from_slot', consumed=previous['loaded'], returned=0,
                                            empty_slot_observed_at=state.get('time'))
                        record['active_fuel_index'] = index;save()
                        load_stack(stage['fuel_item'], 1, stage['fuel_count'], stage)
                        break
                    if time.monotonic() >= wait_until:
                        raise Paused('Previous cooking fuel slot did not empty; no next fuel stage was dispatched')
                    runner.b.wait(.1)
                if not slots[0]['count'] and slots[2]['count'] == batch['amount']:break
            record['stage'] = 'loaded';save()
            deadline = time.monotonic() + batch['amount'] * batch['cooking_ticks'] / 20 + 30
            while True:
                runner.check();state = client.status();slots = state['menu']['slots'][:3]
                balance(state)
                if not slots[0]['count'] and slots[2]['count'] == batch['amount']:
                    break
                if time.monotonic() >= deadline:
                    current = active_fuel()
                    if current is not None:
                        current['consumed_from_slot'] = current['loaded'] - slots[1]['count']
                    record.update(stage='partial_production', pending=None,
                        observed_raw_remaining=slots[0]['count'], observed_output_item=slots[2]['item'],
                        observed_output_in_furnace=slots[2]['count'], observed_fuel_slot=dict(slots[1]),
                        observation_time=state.get('time'))
                    save()
                    raise CookingPartial('Cooking produced only '+str(slots[2]['count'])+'/'+str(batch['amount'])
                        +' in the furnace; partial native result retained without claiming completion')
                runner.b.wait(.25)
            before = _menu_count(state['menu'], batch['output'])
            record.update(stage='output_collecting', pending={'item': batch['output'],
                'count': batch['amount'], 'inventory_before': before});save()
            state = session.click(state, 2, 'quick_move')
            state = session._wait(state, menu['id'], lambda current: not current['cursor']['count']
                and not current['slots'][0]['count'] and not current['slots'][2]['count']
                and _menu_count(current, batch['output']) == before + batch['amount'],
                'cooking_output_inventory', confirmations=2, interval=.1, fresh=True)
            record.update(stage='output_collected', pending=None, verified_output_inventory=before + batch['amount']);save()
            remaining = state['menu']['slots'][1]['count']
            last = active_fuel()
            if remaining:
                if last is None or state['menu']['slots'][1]['item'] != last['fuel_item'] or remaining > last['loaded']:
                    raise Paused('Owned leftover cooking fuel changed')
                before_fuel = _menu_count(state['menu'], last['fuel_item'])
                record.update(stage='fuel_returning', pending={'item': last['fuel_item'],
                    'count': remaining, 'inventory_before': before_fuel,
                    'fuel_stage_index': record['active_fuel_index']});save()
                state = session.click(state, 1, 'quick_move')
                session._wait(state, menu['id'], lambda current: not current['cursor']['count']
                    and not current['slots'][1]['count']
                    and _menu_count(current, last['fuel_item']) == before_fuel + remaining,
                    'cooking_unused_fuel_inventory', confirmations=2, interval=.1, fresh=True)
            if last is not None:last.update(stage='collected', returned=remaining, consumed=last['loaded'] - remaining)
            record.update(stage='collected', pending=None, complete=True,
                          fuel_returned=remaining, fuel_consumed=record['loaded_fuel'] - remaining);save()
            runner.b.close()
            runner.event('cooked_batch', output=batch['output'], count=batch['amount'],
                         fuel=batch['fuel_item'], fuel_count=record['loaded_fuel'],
                         fuel_stages=record['fuel_stages'], journal=str(path))
        except CookingPartial as error:
            record['error'] = str(error);save()
            try:reconcile_partial()
            except (RuntimeError, ValueError, Paused) as failure:
                record['reconciliation_error'] = str(failure);save()
                runner.b.halted = True
                raise Paused('Partial cooking recovery stopped; original pending journal retained: ' + str(failure)) from failure
            runner.event('cooking_partial', source=batch['source'], output=batch['output'],
                         actual_output_inventory_gain=record['reconciled_output_count'],
                         actual_raw_returned=record['reconciled_raw_count'], journal=str(path))
            raise CookingPartial('Cooking recovered only '+str(record['reconciled_output_count'])+'/'+str(batch['amount'])
                +' cooked items and '+str(record['reconciled_raw_count'])
                +' raw items to the backpack; partial result recorded, replan additional fuel') from error
        except (RuntimeError, ValueError, Paused) as error:
            record['error'] = str(error);save()
            runner.b.halted = True
            raise Paused('Cooking SDK stopped; original furnace journal retained: ' + str(error)) from error
    return runner.b.read()
