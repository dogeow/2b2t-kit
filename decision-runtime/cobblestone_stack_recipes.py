"""Exact vanilla cobblestone shape recipes with no container remainders."""

def supported(spec):
    shapes = {
        'minecraft:cobblestone_slab': (6, [1, 2, 3]),
        'minecraft:cobblestone_stairs': (4, [1, 4, 5, 7, 8, 9]),
    }
    shape = shapes.get(spec.get('output'))
    if shape is None:
        return False
    produces, cells = shape
    ingredients = spec.get('ingredients')
    return (spec.get('recipe_id') == spec['output'].removeprefix('minecraft:')
            and type(spec.get('width')) is int and spec['width'] == 3
            and type(spec.get('produces')) is int and spec['produces'] == produces
            and ingredients == {'minecraft:cobblestone': cells}
            and all(type(cell) is int for cell in ingredients['minecraft:cobblestone']))
