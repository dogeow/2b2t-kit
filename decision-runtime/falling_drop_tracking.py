"""Identity-bound observations for a single ordinary mined drop.

The observer does not mine, steer, or claim that an unseen entity despawned.
Callers must keep the original request journal and supply fresh game snapshots.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class DropObservation:
    state: str
    uuid: str | None = None
    position: tuple[float, float, float] | None = None
    reason: str = ''


def _point(value):
    return (isinstance(value,(list,tuple)) and len(value)==3
            and all(type(x) in (int,float) and math.isfinite(x) for x in value))


def observe(*,item,expected_count,before,current,entities,known_ids,origin,tracked_uuid=None,radius=8):
    """Conservatively classify actual inventory and entity data after one mine.

    A known drop may not be substituted by another entity. If the original is
    no longer loaded, it remains unresolved unless the exact inventory delta
    proves pickup. Existing/merged stacks and multiple new candidates are never
    guessed. Entity-absence does not prove expiry or destruction.
    """
    if (not isinstance(item,str) or not item.startswith('minecraft:')
            or type(expected_count)is not int or not 1<=expected_count<=64
            or type(before)is not int or before<0 or type(current)is not int or current<0
            or not isinstance(entities,list) or not isinstance(known_ids,(set,frozenset))
            or not _point(origin) or type(radius) not in (int,float) or not math.isfinite(radius) or not 0<radius<=32
            or tracked_uuid is not None and (not isinstance(tracked_uuid,str) or not tracked_uuid)):
        raise ValueError('Exact item, stock, identity and bounded observations required')
    if current not in (before,before+expected_count):
        return DropObservation('stop',reason='unexpected_inventory_delta')
    candidates=[]
    for e in entities:
        if not isinstance(e,dict) or e.get('type')!='minecraft:item':continue
        uid=e.get('uuid');stack=e.get('stack') or {};position=e.get('pos')
        if not isinstance(uid,str) or not uid or not _point(position):continue
        if uid in known_ids and uid!=tracked_uuid:continue
        if tracked_uuid is not None and uid!=tracked_uuid:continue
        if math.dist(position,origin)>radius:continue
        if stack.get('item')!=item:continue
        if type(stack.get('count'))is not int or stack['count']!=expected_count:
            return DropObservation('stop',uid,tuple(position),'stack_changed_or_merged')
        candidates.append((uid,tuple(position)))
    if len(candidates)>1:return DropObservation('stop',reason='multiple_matching_drops')
    if current==before+expected_count:
        if candidates:return DropObservation('stop',reason='inventory_gain_but_drop_still_visible')
        return DropObservation('collected',tracked_uuid)
    if candidates:
        uid,position=candidates[0];return DropObservation('track',uid,position)
    return DropObservation('unobserved',tracked_uuid,reason='original_drop_not_currently_visible')


def intercept_pose(position, *, minimum_y, vertical_lead=2.0):
    """Candidate underneath a freshly observed falling item; not a path proof."""
    if (not _point(position) or type(minimum_y) not in (int,float) or not math.isfinite(minimum_y)
            or type(vertical_lead) not in (int,float) or not math.isfinite(vertical_lead)
            or not 1<=vertical_lead<=4):raise ValueError('Finite position and bounded lead required')
    y=max(float(minimum_y),float(position[1])-float(vertical_lead))
    if y>=position[1]:return None
    return [float(position[0]),y,float(position[2])]
