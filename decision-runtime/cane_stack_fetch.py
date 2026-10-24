"""Prefer whole storage stacks when withdrawing cane from a live collector."""
def planned_take(deficit,available,capacity,sources):
    if any(type(v)is not int or v<0 for v in (deficit,available,capacity)):
        raise ValueError('Nonnegative observed counts required')
    limit=min(((deficit+63)//64)*64,available,capacity)
    # A full-stack withdrawal avoids the vulnerable return to a source slot
    # which the collector can refill. The deficit is a minimum batch, so one
    # extra partial stack is useful reserve; never round above carrying capacity.
    full=0
    for row in sources:
        if row.get('item')!='minecraft:sugar_cane' or not row.get('count'):continue
        if row['count']!=64:break
        if full+64>limit:break
        full+=64
    return full if full else limit//3*3
