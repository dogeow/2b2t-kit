"""Capacity hint only; ownership, health and actual transfers remain caller guards."""
def recovery_space_ready(state):
    """A new nonstacking bed plus a borrowed roof block require two carry slots."""
    rows=[row for row in state.get('inventory',[])
          if isinstance(row,dict)and type(row.get('slot'))is int and 0<=row['slot']<36]
    return (len(rows)==36 and {row['slot']for row in rows}==set(range(36))
            and all(type(row.get('count'))is int and row['count']>=0 for row in rows)
            and sum(row['count']==0 for row in rows)>=2)
