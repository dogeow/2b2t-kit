"""Prefer complete source stacks over a hopper's freshly replenished trickle."""
def choose(rows,item,*,deposit=False):
    candidates=[r for r in rows if r['item']==item and r['count']>0]
    return (next(iter(candidates),None)if deposit else max(candidates,key=lambda r:r['count'],default=None))
