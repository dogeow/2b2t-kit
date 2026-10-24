"""Check the actual public barrier for quote reads; never authorize a reset."""
import math
from village_adult_enclosure import audit

def require(room,slot,scene):
    rows={tuple(r['pos']):r for r in scene['blocks']}
    if(slot.get('counter_configuration')!='bottom_slab_and_full_upper_cap'
       or slot.get('counter_block')is None):
        room.require_caps(rows)
        return {'scope':'quote_observation_only_not_lectern_reset','kind':'workpoint_caps'}
    front=slot.get('counter_block');floor=room.floor_y
    if(not isinstance(front,list)or len(front)!=3 or any(type(v)is not int for v in front)
       or tuple(front)!=(room.public_counter or room.work)or front[0]!=room.work[0]
       or front[1]!=floor or room.work[1]!=floor):
        raise ValueError('Exact separate public counter geometry required')
    depth=(room.work[2]-front[2])*room.inward
    if depth not in (1,2,3,4):raise ValueError('Private workpoint must be inside the public enclosure')
    x,y,z=front
    if(rows.get((x,y,z),{}).get('solid')is not True
       or rows.get((x,y+1,z),{}).get('state')!='Block{minecraft:dark_oak_slab}[type=bottom,waterlogged=false]'
       or rows.get((x,y+2,z),{}).get('solid')is not True):
        raise ValueError('Separate public counter layers are not intact')
    result=audit(rows,front=front,floor=floor,inward=room.inward,depth=depth)
    if not result['verified']:raise ValueError('Separate public counter enclosure is not closed')
    actor=room.actor(scene);box=actor.get('bounds')or{};lo=[x,floor,min(z+room.inward,z+depth*room.inward)];hi=[x+1,floor+3,max(z+room.inward,z+depth*room.inward)+1]
    if(any(not isinstance(box.get(k),list)or len(box[k])!=3 for k in ('min','max'))
       or any(type(v)not in(int,float)or not math.isfinite(v)for k in ('min','max')for v in box[k])
       or not all(a<=b<c<=d for a,b,c,d in zip(lo,box['min'],box['max'],hi))):
        raise ValueError('Exact adult body is not inside the separate public enclosure')
    return {'scope':'quote_observation_only_not_lectern_reset','kind':'explicit_separate_public_counter','physical_enclosure':result}
