"""One registered native sea-water refill for an existing mud backend/controller."""
import math
from material_plan import inventory_counts
from .protocol import JobBlocked

def fill(backend, target):
    c=backend.ensure_client();state=c.status();count=inventory_counts(state).get('minecraft:water_bucket',0)
    if count>=target:return {'phase':'done','water_bucket':count,'new_use':False}
    cfg=backend.profile.get('mud_bucket_source')or{}
    pos,approach=cfg.get('pos'),cfg.get('approach')
    if (target!=1 or cfg.get('authorized')is not True or cfg.get('renewing_source_server_verified')is not True
            or not isinstance(pos,list)or len(pos)!=3 or any(type(n)is not int for n in pos)
            or not isinstance(approach,list)or len(approach)!=3 or any(type(n)not in (int,float)or not math.isfinite(n)for n in approach)
            or cfg.get('expected_state')!='Block{minecraft:water}[level=0]'):
        raise JobBlocked('Mud refill requires one explicitly registered verified renewing source')
    if inventory_counts(state).get('minecraft:bucket',0)!=1:
        raise JobBlocked('Mud refill requires one actual singleton empty bucket')
    backend.checkpoint();scan=c.checked('scan',min=pos,max=pos,details=True)
    if len(scan['blocks'])!=1 or scan['blocks'][0]['state']!=cfg['expected_state']:
        raise JobBlocked('Registered mud sea-water source changed; no use sent')
    # A diagonal descent sweeps neighbouring one-block-higher ground. Keep the
    # actual current height for the short horizontal leg, then descend only
    # inside the registered clear sand-bank column.
    pose=c.status()['pos']
    if pose[1]>approach[1]+.25 and math.hypot(pose[0]-approach[0],pose[2]-approach[2])>.25:
        c.checked('navigate',target=[approach[0],pose[1],approach[2]],arrival=.15,air_only=True,seconds=20)
    c.checked('navigate',target=approach,arrival=.15,air_only=True,seconds=20)
    c.checked('select_item',item='minecraft:bucket')
    receipt=c.checked('bucket_fill',pos=pos,expected_state=cfg['expected_state'],expected_hand='minecraft:bucket')
    after=c.status();fresh=c.checked('scan',min=pos,max=pos,details=True)
    if (inventory_counts(after).get('minecraft:water_bucket',0)!=1
            or not fresh.get('blocks')or fresh['blocks'][0]['state']!=cfg['expected_state']):
        raise JobBlocked('Mud water inventory or renewing source outcome is unproved; do not repeat')
    return {'phase':'done','water_bucket':1,'native_receipt':receipt,'source_still_renewed':True,
            'farm_water_untouched':True,'new_use':True}
