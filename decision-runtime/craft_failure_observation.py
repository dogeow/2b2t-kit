"""Narrow read-only observation of a settled interrupted inventory craft."""
from material_plan import inventory_counts


def settled(command, error, failure, event, first, second, world, task, quarantined_missing=None):
    observed = failure.get('observed', {})
    owned = failure.get('owned_inventory_crafting', {})
    expected = inventory_counts({'inventory': observed.get('inventory', [])})
    missing = quarantined_missing or {}
    if not isinstance(missing, dict) or any(not isinstance(k,str) or type(v) is not int or v <= 0 or expected[k] < v for k,v in missing.items()):
        return False
    recipe = failure.get('recipe') or {}
    recipe_items = set((recipe.get('ingredients') or {}).keys()) | {recipe.get('output')}
    if missing and (first.get('game_interaction', {}).get('last_interaction_at', 0) <= observed.get('time', 0)
                    or any(k in recipe_items for k in missing)):
        return False
    expected.subtract(missing)
    expected += __import__('collections').Counter()
    def safe(s):
        menu = s.get('menu') or {}
        slots = menu.get('slots') or []
        lease = s.get('supervision_lease') or {}
        return (s.get('world_session') == world and s.get('connected') is True
                and s.get('health') == 20 and s.get('manual_movement') is False
                and not s.get('screen') and menu.get('type') == 'InventoryMenu'
                and menu.get('cursor', {}).get('count') == 0 and len(slots) >= 5
                and all(v.get('count') == 0 for v in slots[:5])
                and inventory_counts(s) == expected and lease.get('job_session') == task
                and s.get('last_request') == error.get('last_request')
                and not s.get('navigating') and not s.get('native_material_busy') and not s.get('pending_scan'))
    return bool(command.get('action') == 'manufacture'
        and error.get('error') == 'Inventory acknowledgement missing at ingredient_pickup; no action replay'
        and error.get('native_inflight') is None and error.get('unconfirmed_native_request') is None
        and failure.get('detail') == error.get('error') and owned.get('world_session') == world
        and owned.get('task_session') == task and owned.get('menu_id') == 0
        and observed.get('world_session') == world and observed.get('menu_id') == 0
        and observed.get('cursor', {}).get('count') == 0
        and len(observed.get('grid', [])) == 5 and all(v.get('count') == 0 for v in observed['grid'])
        and event.get('request_id') == error.get('last_request') and event.get('op') == 'slot_click'
        and event.get('phase') == 'done' and event.get('world_session') == world
        and event.get('params', {}).get('task_session') == task and event.get('inventory_delta') == {}
        and event.get('revision_before') == event.get('revision_after') == first.get('control_revision') == second.get('control_revision')
        and type(first.get('time')) is int and type(second.get('time')) is int and second['time'] > first['time']
        and safe(first) and safe(second))
