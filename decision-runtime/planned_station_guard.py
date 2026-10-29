"""Read-only guard for a planned damaging block directly below a print station."""
import math

class UnsafePlannedStation(RuntimeError):
    def __init__(self,position,target):
        self.position=position;self.target=target
        super().__init__('施工站位与计划岩浆块同列且过近；已阻止继续打印，先换到安全侧面')

def require_safe_planned_station(state,cells):
    hazards=[r for r in(cells or [])if isinstance(r,dict)and r.get('expected')=='Block{minecraft:magma_block}']
    if not hazards:return
    pos=state.get('pos')if isinstance(state,dict)else None
    if (not isinstance(pos,list)or len(pos)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in pos)):
        raise UnsafePlannedStation(pos,None)
    low_x,high_x=math.floor(pos[0]-.3+1e-7),math.floor(pos[0]+.3-1e-7)
    low_z,high_z=math.floor(pos[2]-.3+1e-7),math.floor(pos[2]+.3-1e-7)
    for row in hazards:
        p=row.get('pos')
        if not isinstance(p,list)or len(p)!=3 or any(type(v)is not int for v in p):
            raise UnsafePlannedStation(pos,p)
        # Keep the whole player footprint off the hazard column, including a
        # short hover. This supplements, never acknowledges or relaxes, native safety.
        if (low_x<=p[0]<=high_x and low_z<=p[2]<=high_z
                and p[1]<pos[1]+1.8 and p[1]+1>=pos[1]-3):
            raise UnsafePlannedStation(pos,p)
