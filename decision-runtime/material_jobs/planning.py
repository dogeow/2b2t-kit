"""Reuse installed recipes; add only the vanilla concrete-hardening dependency."""
from collections import defaultdict
import copy

from material_plan import MaterialPlanner, quantities
from recipe_catalog import Recipe

COLORS = ('white', 'orange', 'magenta', 'light_blue', 'yellow', 'lime', 'pink',
          'gray', 'light_gray', 'cyan', 'purple', 'blue', 'brown', 'green', 'red', 'black')


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
                   'minecraft:lapis_lazuli','minecraft:redstone','minecraft:emerald','minecraft:bone_meal'} - processed
    if stock.get('minecraft:bone_block',0) or hint.get('minecraft:bone_block',0):
        # The reverse nine-meal packing recipe must not turn this known depot
        # source into a dependency cycle or imaginary directly gathered meal.
        acquisition.add('minecraft:bone_block')
    result = MaterialPlanner(expanded, acquisition_items=acquisition).plan(targets, stock)
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
