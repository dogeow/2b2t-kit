"""Align the actual player horizontally before traversing a one-cell roof hatch."""
import math

def column_aligned(position,roof):
    return (isinstance(position,list)and len(position)==3
            and all(type(v)in(int,float)and math.isfinite(v)for v in position)
            and abs(position[0]-(roof[0]+.5))<=.17
            and abs(position[2]-(roof[2]+.5))<=.17)

def traverse_opening(builder,roof,foot_y):
    if(not isinstance(roof,list)or len(roof)!=3 or any(type(v)is not int for v in roof)
            or type(foot_y)not in(int,float)or not math.isfinite(foot_y)):
        raise ValueError('Integer roof cell and finite destination height required')
    before=builder.check()['pos']
    if not isinstance(before,list)or len(before)!=3 or not all(type(v)in(int,float)and math.isfinite(v)for v in before):
        raise RuntimeError('Current hatch approach position is unavailable')
    # Ground walking can coast beyond its arrival radius. A diagonal ascent's
    # body sweep would then intersect the neighbouring, still intact roof.
    builder.nav([roof[0]+.5,before[1],roof[2]+.5])
    aligned=builder.check()['pos']
    if not column_aligned(aligned,roof):
        raise RuntimeError('Player is not centred in the hatch; no vertical input sent')
    reply=builder.nav([roof[0]+.5,foot_y,roof[2]+.5])
    return {'from':before,'aligned':aligned,'destination_height':foot_y,'receipt':reply}
