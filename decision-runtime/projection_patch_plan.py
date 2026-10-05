"""Bound one print mask to a connected prefix of currently observed AIR targets.

This is a work plan. Every placement still needs the native printer's actual
anchor, server acknowledgement, physical scene and inventory acceptance.
"""
import heapq


def _points(values):
    result = set()
    for p in values:
        if not isinstance(p, (list, tuple)) or len(p) != 3 or any(type(v) is not int for v in p):
            raise ValueError('Exact integer block coordinates required')
        result.add(tuple(p))
    return result


def connected_mask(missing, correct, low, high, budget, *, excluded=()):
    """Each chosen target touches actual correct terrain or an earlier target.

    Targets and support come from a complete live scene. The returned ordering
    is a dependency prefix, so clipping the stock budget cannot remove all of
    the currently supported roots. Disconnected components remain unselected.
    """
    low, high = next(iter(_points([low]))), next(iter(_points([high])))
    if (low[1] != high[1] or any(low[i] > high[i] for i in range(3))
            or high[0]-low[0] > 3 or high[2]-low[2] > 3
            or type(budget) is not int or not 1 <= budget <= 16):
        raise ValueError('One horizontal 4x4 patch and stock budget1..16 required')
    missing, correct, excluded = _points(missing), _points(correct), _points(excluded)
    if missing & correct:
        raise ValueError('A target cannot be both observed AIR and actual correct')
    candidates = {p for p in missing - excluded if all(low[i] <= p[i] <= high[i] for i in range(3))}
    def neighbors(p):
        x,y,z=p
        return ((x-1,y,z),(x+1,y,z),(x,y,z-1),(x,y,z+1))
    def priority(p):
        return ((2*p[0]-low[0]-high[0])**2+(2*p[2]-low[2]-high[2])**2, p[2], p[0])
    roots = {p for p in candidates if any(n in correct for n in neighbors(p))}
    queue = [(priority(p),p) for p in roots]
    heapq.heapify(queue)
    queued, selected = set(roots), []
    while queue and len(selected) < budget:
        _,p=heapq.heappop(queue)
        selected.append(p)
        for n in neighbors(p):
            if n in candidates and n not in queued:
                queued.add(n)
                heapq.heappush(queue,(priority(n),n))
    return selected
