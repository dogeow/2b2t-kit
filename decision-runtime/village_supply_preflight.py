"""Recover space before a renewable supply trip, with ordinary exact merges."""
def prepare_chop_inventory(client, checkpoint):
    from material_stack_consolidation import prepare_fetch
    def free(state):
        rows = [r for r in state.get('inventory', []) if 0 <= r.get('slot', 99) < 36]
        if len(rows) != 36 or {r['slot'] for r in rows} != set(range(36)):
            raise RuntimeError('Complete main inventory is required before tree harvest')
        return sum(not r.get('count') for r in rows)
    initial = checkpoint()
    if free(initial) >= 3:
        return None
    result = prepare_fetch(client, ('minecraft:dark_oak_log', 'minecraft:dark_oak_sapling'))
    if free(checkpoint()) < 3:
        raise RuntimeError('Store spare supplies first: native tree harvest reserves three empty main slots')
    return result
