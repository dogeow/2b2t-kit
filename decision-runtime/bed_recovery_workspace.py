"""Capacity hints only; ownership, health and actual transfers remain caller guards."""
def _carry_rows(state):
    rows=[row for row in state.get('inventory',[])
          if isinstance(row,dict)and type(row.get('slot'))is int and 0<=row['slot']<36]
    if (len(rows)!=36 or {row['slot']for row in rows}!=set(range(36))
            or any(type(row.get('count'))is not int or row['count']<0 for row in rows)):
        return None
    return rows


def recovery_space_ready(state):
    """A new nonstacking bed plus a borrowed roof block require two carry slots."""
    rows=_carry_rows(state)
    return rows is not None and sum(row['count']==0 for row in rows)>=2


def plain_recovery_space_ready(state,item):
    """One ordinary block drop needs an empty slot or a witnessed plain stack."""
    rows=_carry_rows(state)
    if rows is None or not isinstance(item,str)or not item.startswith('minecraft:'):
        return False
    return any(row['count']==0 or (
        row.get('item')==item and set(row)<={'slot','item','count','max_stack'}
        and type(row.get('max_stack'))is int and 0<row['count']<row['max_stack']<=64)
        for row in rows)
