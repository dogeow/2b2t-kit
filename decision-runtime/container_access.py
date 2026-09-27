"""Open a verified outdoor chest from above without Flight drifting during the server reply."""
import math
import time
import json


def open_grounded_chest(client, pos, block_id='minecraft:chest', *, allow_empty=False):
    if block_id not in ('minecraft:chest','minecraft:ender_chest'):
        raise ValueError('Only ordinary or Ender chests use this landing approach')
    x,y,z=pos
    rows=client.request('scan',min=pos,max=[x,y+6,z],details=True)['blocks']
    expected=next((r['state'] for r in rows if r['pos']==pos),'')
    if not expected.startswith('Block{'+block_id+'}'):
        raise RuntimeError('Expected outdoor chest changed')
    if any(r['pos'][1]>y and r['state']!='Block{minecraft:air}' for r in rows):
        raise RuntimeError('Chest landing column is obstructed')
    if client.status()['hand']['item']!='minecraft:diamond_sword':
        client.checked('select_item',item='minecraft:diamond_sword')
    # Cruise can finish with horizontal momentum and a one-block arrival radius.
    # Use the collision-aware block approach before disabling Flight to land.
    client.checked('approach_block',pos=pos,face='up',expected_state=expected,stand_distance=.65,seconds=90)
    client.checked('walk',target=[x+.5,y+1,z+.5],arrival=.35,restore_flight=False,seconds=20)
    until=time.monotonic()+4
    while True:
        state=client.request('snapshot')
        if state['health']<19:raise RuntimeError('Health changed before opening storage')
        if state.get('on_ground') and math.hypot(state['velocity'][0],state['velocity'][2])<.03:break
        if time.monotonic()>=until:raise RuntimeError('Chest approach did not settle on the ground')
        time.sleep(.15)
    client.checked('interact',pos=pos,face='up',expected_state=expected,expected_hand='minecraft:diamond_sword')
    return wait_container_contents(client,'ChestMenu',require_nonempty=not allow_empty)


def wait_container_contents(client,kind,require_nonempty=True):
    # A fixed eight-tick native interaction receipt is not a server-open receipt.
    # On a lagging server, stay at the verified chest until its menu actually arrives.
    until=time.monotonic()+20
    previous=None;stable_since=None
    while True:
        state=client.request('snapshot');menu=state['menu']
        if menu['type']==kind:
            if menu['cursor']['count']:raise RuntimeError('Storage cursor is occupied')
            client.owned_material_menu=menu['id']
            slots=menu['slots'][:-36]
            signature=json.dumps(slots,sort_keys=True)
            if not require_nonempty or any(row.get('count',0) for row in slots):
                if signature==previous and stable_since is not None and time.monotonic()-stable_since>=1:
                    return state
                if signature!=previous:stable_since=time.monotonic()
            else:stable_since=None
            previous=signature
        if time.monotonic()>=until:raise RuntimeError('Chest opening was not acknowledged')
        time.sleep(.5)
