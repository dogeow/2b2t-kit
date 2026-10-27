"""Separate verified construction changes from observed off-model grass spreading.

Only dirt-to-grass outside every planned non-air cell is incidental. This does
not prove its cause, authorize a replay, or replace queue/stock confirmation.
"""
DIRT='Block{minecraft:dirt}'
GRASS='Block{minecraft:grass_block}[snowy=false]'

def classify(before,after,expected,targets):
    changed={p for p in before.keys()|after.keys() if before.get(p)!=after.get(p)}
    completed={p for p,state in targets.items() if before.get(p)!=state and after.get(p)==state}
    incidental={p for p in changed-completed if p not in expected and p not in targets
                and before.get(p)==DIRT and after.get(p)==GRASS}
    return {'completed':completed,'incidental_grass':incidental,'unexpected':changed-completed-incidental}
