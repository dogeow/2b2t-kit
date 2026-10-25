"""Reachable 2x2 spruce growth stances outside the vanilla mega-pine leaf mask.

Both installed mega-spruce configurations use radius0 and a 3.5-scaled crown
with at most one extra row radius: at most4. Signed double-trunk offsets are
folded towards the two central columns. The diagonal (3,3) is excluded even
from radius4 because 3*3+3*3>4*4. This avoids relying on a post-growth escape.
"""
import math

def _root(root):
    if not isinstance(root,(list,tuple))or len(root)!=3 or any(type(v)is not int for v in root):
        raise ValueError('Exact northwest two-by-two root required')

def body_clear(root,pose,*,radius=4):
    _root(root)
    if radius!=4:raise ValueError('Only the inspected vanilla radius4 envelope is supported')
    if not isinstance(pose,(list,tuple))or len(pose)!=3 or any(type(v)not in(int,float)or not math.isfinite(v)for v in pose):return False
    for x in range(math.floor(pose[0]-.3),math.floor(pose[0]+.3-1e-7)+1):
        for z in range(math.floor(pose[2]-.3),math.floor(pose[2]+.3-1e-7)+1):
            dx,dz=x-root[0],z-root[2]
            if dx in(0,1)and dz in(0,1):return False
            a=min(abs(dx),abs(dx-1));b=min(abs(dz),abs(dz-1))
            if a+b<7 and a*a+b*b<=radius*radius:return False
    return True

def candidates(root):
    _root(root);x,y,z=root;result=[]
    for dx,dz,tx,tz,face in[(-2.4,-2.4,0,0,'west'),(4.4,-2.4,1,0,'east'),
                           (-2.4,4.4,0,1,'west'),(4.4,4.4,1,1,'east')]:
        pose=[x+dx,y,z+dz];target=[x+tx,y,z+tz]
        # Native SaplingBlock outline spans1/8..7/8 horizontally and0..0.8 vertically.
        aim=[target[0]+(.125 if face=='west'else .875),y+.4,target[2]+.5]
        eye=[pose[0],pose[1]+1.62,pose[2]]
        if body_clear(root,pose)and math.dist(eye,aim)<4.3:
            result.append({'pose':pose,'target':target,'face':face,'aim':aim})
    return result
