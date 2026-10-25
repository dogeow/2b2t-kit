"""Place distant roots first so existing seedlings do not hide nearer soil faces."""
import math

def planting_order(plants,position):
    """Plant distant roots before nearby seedlings can obscure their soil face."""
    if (not isinstance(position,list)or len(position)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in position)
            or any(not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p)for p in plants)
            or len({tuple(p)for p in plants})!=len(plants)):
        raise ValueError('Distinct integer roots and current finite player position required')
    return sorted(plants,key=lambda p:(-sum((p[i]+.5-position[i])**2 for i in(0,2)),p))

