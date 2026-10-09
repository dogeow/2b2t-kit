"""Choose a currently carried sword for normal container interaction."""
SWORDS = ('minecraft:netherite_sword', 'minecraft:diamond_sword', 'minecraft:iron_sword',
          'minecraft:stone_sword', 'minecraft:copper_sword', 'minecraft:golden_sword', 'minecraft:wooden_sword')


def select_container_hand(client):
    state = client.status()
    current = (state.get('hand') or {}).get('item')
    if current in SWORDS:
        return current
    rows = state.get('inventory')
    if not isinstance(rows, list):
        raise RuntimeError('Current carried inventory is required to choose a container hand')
    present = {row.get('item') for row in rows if row.get('slot', 99) < 36 and row.get('count', 0) > 0}
    item = next((item for item in SWORDS if item in present), None)
    if item is None:
        raise RuntimeError('No carried sword for normal container interaction')
    client.checked('select_item', item=item)
    if (client.status().get('hand') or {}).get('item') != item:
        raise RuntimeError('Selected container hand was not confirmed')
    return item
