"""Exact, remainder-free vanilla storage recipes eligible for stack crafting."""
PLANKS=frozenset(f'minecraft:{wood}_planks' for wood in (
    'oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry',
    'pale_oak','bamboo','crimson','warped'))


def supported(spec):
    output=spec.get('output')
    if output not in ('minecraft:chest','minecraft:hopper'):
        return False
    ingredients=spec.get('ingredients')
    if (spec.get('recipe_id')!=output.removeprefix('minecraft:')
            or type(spec.get('width')) is not int or spec['width']!=3
            or type(spec.get('produces')) is not int or spec['produces']!=1
            or not isinstance(ingredients,dict) or not ingredients
            or any(not isinstance(cells,list) or not cells
                   or any(type(cell) is not int for cell in cells)
                   for cells in ingredients.values())):
        return False
    if output=='minecraft:hopper':
        return ingredients=={'minecraft:iron_ingot':[1,3,4,6,8],
                             'minecraft:chest':[5]}
    return (set(ingredients)<=PLANKS
            and sorted(cell for cells in ingredients.values() for cell in cells)
            ==[1,2,3,4,6,7,8,9])
