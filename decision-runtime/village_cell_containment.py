"""Prove exactly one expected adult is fully behind a counter before sealing it.

Centre coordinates are only a search hint. A fresh room scan must include every
villager whose body intersects the room or its open counter, so two residents
cannot accidentally be sealed in one cell.
"""
import math

def ready_resident(entities, expected_uuids, x, back_z, front_z):
    if not isinstance(expected_uuids,(set,frozenset))or not expected_uuids:
        raise ValueError('Exact remaining resident identities required')
    villagers=[e for e in entities if e.get('type')=='minecraft:villager']
    if len(villagers)!=1:return None
    v=villagers[0];box=v.get('bounds')or{}
    if(v.get('uuid')not in expected_uuids or v.get('health')!=20 or v.get('is_baby')is not False
       or v.get('alive')is not True):return None
    for side in ('min','max'):
        if(not isinstance(box.get(side),list)or len(box[side])!=3
           or any(type(n)not in(int,float)or not math.isfinite(n)for n in box[side])):return None
    if any(box['min'][i]>=box['max'][i]for i in range(3)):return None
    if not(x+.01<=box['min'][0]<box['max'][0]<=x+.99
           and back_z+.01<=box['min'][2]<box['max'][2]<=front_z-.02):return None
    return v
