"""One registered native sea-water refill for an existing mud backend/controller."""
import math
import time
from material_plan import inventory_counts
from .protocol import JobBlocked

BOTTLE_SCOPE='single_normal_bottle_use_current_connection_exact_hand_and_water_potion_slot_server_packets_source_unchanged_prediction_settled_inventory_delta_after_8_ticks'


def bottle_source(backend):
    cfg=backend.profile.get('mud_bucket_source')or{}
    pos,approach=cfg.get('pos'),cfg.get('approach')
    if (cfg.get('authorized')is not True or not isinstance(pos,list)or len(pos)!=3
            or any(type(n)is not int for n in pos)or not isinstance(approach,list)or len(approach)!=3
            or any(type(n)not in (int,float)or not math.isfinite(n)for n in approach)
            or cfg.get('expected_state')!='Block{minecraft:water}[level=0]'):
        raise JobBlocked('Direct bottle fill needs explicitly registered source water and a dry approach')
    return cfg


def fill_bottle(backend):
    """Use the existing material controller once; prove an exact new water slot."""
    c=backend.ensure_client();cfg=bottle_source(backend);pos,approach=cfg['pos'],cfg['approach']
    if c.status().get('bottle_water_protocol',0)<1:
        raise JobBlocked('Direct source-water bottle protocol requires the updated Kit host')
    # Share the registered water route; nearby work never rises to cruise height.
    pose=c.status()['pos']
    if math.dist(pose,approach)>6:
        from .acquisition import _travel
        from .navigation import lift_for_travel
        backend.prepare_travel();lift_for_travel(c)
        _travel(c,[approach[0],max(c.status()['pos'][1],approach[1]+24),approach[2]],backend.checkpoint,[],keep_cruise=True)
    pose=c.status()['pos']
    if pose[1]>approach[1]+.25 and math.hypot(pose[0]-approach[0],pose[2]-approach[2])>.25:
        c.checked('navigate',target=[approach[0],pose[1],approach[2]],arrival=.15,air_only=True,seconds=20)
    c.checked('navigate',target=approach,arrival=.15,air_only=True,seconds=20)
    backend.checkpoint();fresh=c.checked('scan',min=pos,max=pos,details=True)
    if (fresh.get('world_session')!=c.world or len(fresh.get('blocks',[]))!=1
            or fresh['blocks'][0].get('pos')!=pos or fresh['blocks'][0].get('state')!=cfg['expected_state']):
        raise JobBlocked('Registered bottle source changed; no use sent')
    c.checked('select_item',item='minecraft:glass_bottle')
    before=c.status();receipt=c.checked('bottle_fill',pos=pos,expected_state=cfg['expected_state'],expected_hand='minecraft:glass_bottle')
    after=c.status();proof=receipt.get('bottle_water')or{};slot=proof.get('water_slot')
    old,new=inventory_counts(before),inventory_counts(after)
    water=next((r for r in after['inventory']if r.get('slot')==slot),None)
    if (receipt.get('phase')!='done' or not isinstance(receipt.get('id'),str) or not receipt['id']
            or proof.get('world_session')!=c.world or proof.get('request_id')!=receipt.get('id')
            or proof.get('operation')!='bottle_fill' or proof.get('pos')!=pos or proof.get('use_count')!=1
            or proof.get('confirmed')is not True or proof.get('unknown_outcome')is not False
            or proof.get('server_hand_confirmed')is not True or proof.get('server_water_slot_confirmed')is not True
            or proof.get('potion')!='minecraft:water' or proof.get('confirmation_scope')!=BOTTLE_SCOPE
            or proof.get('source_not_consumed_by_bottle_use')is not True
            or old['minecraft:glass_bottle']-new['minecraft:glass_bottle']!=1 or new['minecraft:potion']-old['minecraft:potion']!=1
            or water is None or water.get('item')!='minecraft:potion' or water.get('count')!=1
            or type(slot)is not int or not 0<=slot<36):
        raise JobBlocked('Single source-water bottle result unproved; preserve original receipt and never repeat')
    return {'phase':'done','native_receipt':receipt,'derived_water_slot':water,'source_preserved':True,'new_use':True}

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
    after=c.status()
    if inventory_counts(after).get('minecraft:water_bucket',0)!=1:
        raise JobBlocked('Mud filled bucket inventory is unproved; do not repeat')
    deadline=time.monotonic()+4
    while True:
        backend.checkpoint();fresh=c.checked('scan',min=pos,max=pos,details=True)
        if fresh.get('blocks')and fresh['blocks'][0]['state']==cfg['expected_state']:break
        if time.monotonic()>=deadline:
            raise JobBlocked('Mud renewing source outcome is unproved after one confirmed fill; do not repeat')
        time.sleep(.15)
    if inventory_counts(c.status()).get('minecraft:water_bucket',0)!=1:
        raise JobBlocked('Mud water inventory or renewing source outcome is unproved; do not repeat')
    return {'phase':'done','water_bucket':1,'native_receipt':receipt,'source_still_renewed':True,
            'farm_water_untouched':True,'new_use':True}
