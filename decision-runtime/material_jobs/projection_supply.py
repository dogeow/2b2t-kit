"""Pure validation for projection items that can be staged for immediate placement."""

from collections import Counter
import re

from material_plan import quantities


def direct_air_supply(audit, needed, posts=None):
    """Cap schema-2 item counts to verified, empty, dry projection cells.

    This is deliberately independent of warehouse and inventory code so both
    the backend that withdraws stock and the scheduler that accepts its receipt
    enforce the same boundary.
    """
    if type(audit.get('audit_schema')) is int and audit['audit_schema'] == 1:
        return dict(needed)
    if type(audit.get('audit_schema')) is not int or audit['audit_schema'] != 2:
        return {}
    rows=audit.get('mismatches');kinds=audit.get('kinds')
    matched=audit.get('matched');total=audit.get('total')
    if (audit.get('loaded_chunks_verified') is not True or not isinstance(rows,list)
            or not isinstance(kinds,dict) or type(matched) is not int or type(total) is not int
            or matched<0 or total<1 or matched+len(rows)!=total):
        return {}
    advertised=dict(quantities(audit.get('replacement_items',{})))
    observed_kinds=Counter();mapped=Counter();air=Counter()
    block_item_aliases={'minecraft:potatoes':'minecraft:potato',
                        'minecraft:wheat':'minecraft:wheat_seeds',
                        'minecraft:beetroots':'minecraft:beetroot_seeds',
                        'minecraft:water_cauldron':'minecraft:cauldron'}
    for row in rows:
        if not isinstance(row,dict) or row.get('kind') not in ('missing','occupied','state_only'):
            return {}
        observed_kinds[row['kind']]+=1
        expected=row.get('expected')
        if not isinstance(expected,str):
            return {}
        if row['kind']=='state_only' or 'half=upper' in expected or 'part=head' in expected:
            continue
        match=re.match(r'^Block\{([a-z0-9_.-]+:[a-z0-9_./-]+)\}',expected)
        if not match:
            return {}
        block=match.group(1)
        if block in ('minecraft:water','minecraft:lava'):
            continue
        item=block_item_aliases.get(block,block);mapped[item]+=1
        if (row.get('kind')=='missing' and row.get('actual') in ('Block{minecraft:air}','Block{minecraft:cave_air}')
                and row.get('fluid') is False and row.get('block_entity') is False
                and row.get('neighbors_loaded') is True and row.get('adjacent_fluid') is False):
            air[item]+=1
    if (set(kinds)-{'missing','occupied','state_only'}
            or any(type(count) is not int or count<0 for count in kinds.values())
            or dict(observed_kinds)!={kind:count for kind,count in kinds.items() if count}
            or dict(mapped)!=advertised):
        return {}
    result={}
    for item,count in needed.items():
        if air[item]:
            result[item]=min(count,air[item])
    return result
