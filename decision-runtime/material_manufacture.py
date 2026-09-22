"""Execute freshly planned crafting dependencies under an existing MaterialClient lease."""
from collections import Counter
import json
import time

import craft_recipe
from material_plan import MaterialPlanner, inventory_counts
from safety_interlock import require_unlocked


def manufacture(client, catalog, targets, keep=None, allow_partial=False):
    # A historical offline plan is never accepted as an execution request.
    snapshot = client.status()
    require_unlocked(client.root, snapshot)
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
        if snapshot.get('menu', {}).get('type') != 'CraftingMenu':
            raise RuntimeError('Workbench menu changed; manufacturing stopped')
        spec = {'recipe_id': step['recipe_id'], 'output': step['item'],
                'produces': step['produces_per_recipe'], 'width': step['width'],
                'ingredients': step['grid'], 'missing_for_one': {}}
        try:
            after = craft_recipe.execute(client, spec, stock[step['item']] + produced)
        except craft_recipe.InventoryCapacity:
            results.append({'item':step['item'],'state':'waiting_for_inventory_space'})
            continue
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
