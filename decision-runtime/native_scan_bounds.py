"""Inclusive native scan limits; tiles remain distinct real observations, never one fake frame."""
import math

MAX_CELLS=50_000

def sizes(low,high):
    if (not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3
        or any(type(v)is not int for v in low+high)or any(a>b for a,b in zip(low,high))):
        raise ValueError('Three ordered integer scan coordinates required')
    return [b-a+1 for a,b in zip(low,high)]

def validate(low,high):
    count=math.prod(sizes(low,high))
    if count>MAX_CELLS:raise ValueError('Native scan exceeds 50000 cells; use separate bounded tiles')
    return count

def tiles(low,high):
    dims=sizes(low,high)
    if math.prod(dims)<=MAX_CELLS:
        yield list(low),list(high);return
    axis=max(range(3),key=dims.__getitem__);middle=(low[axis]+high[axis])//2
    left=list(high);left[axis]=middle;right=list(low);right[axis]=middle+1
    yield from tiles(low,left);yield from tiles(right,high)
