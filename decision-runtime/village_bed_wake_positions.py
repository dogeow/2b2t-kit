"""Horizontal bed wake candidates audited against the installed 26.2 BedBlock.

These are candidate cells, not safe landing positions. Builders must inspect
real collision shapes and verify a real wake before claiming containment.
"""


def possible_wake_cells(head, foot):
    for point in (head, foot):
        if not isinstance(point, (list, tuple)) or len(point) != 3 or any(type(v) is not int for v in point):
            raise ValueError('Integer head and foot block coordinates required')
    dx, dz = head[0] - foot[0], head[2] - foot[2]
    if head[1] != foot[1] or abs(dx) + abs(dz) != 1:
        raise ValueError('One adjacent horizontal bed required')
    sx, sz = -dz, dx
    offsets = ((sx, sz), (sx-dx, sz-dz), (sx-2*dx, sz-2*dz),
               (-2*dx, -2*dz), (-sx-2*dx, -sz-2*dz), (-sx-dx, -sz-dz),
               (-sx, -sz), (-sx+dx, -sz+dz), (dx, dz), (sx+dx, sz+dz),
               (0, 0), (-dx, -dz))
    return frozenset((head[0]+x, head[1], head[2]+z) for x, z in offsets)
