"""Shared exact repair-input identity including applied enchantments."""
def enchantments(row):
    return {e['id']:e['level'] for e in row.get('enchantments',[])}


def identity(row):
    return (row.get('item'),row.get('count'),row.get('durability'),row.get('max_durability'),tuple(sorted(enchantments(row).items())))
