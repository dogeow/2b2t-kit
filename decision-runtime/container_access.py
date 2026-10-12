"""Open a verified outdoor chest from above without Flight drifting during the server reply."""
import math
import time
import json
from pathlib import Path
from container_hand import select_container_hand


class OutdoorChestChanged(RuntimeError):
    """A registered source failed its read-only block scan before approach."""

    def __init__(self, pos, block_id, observed_state, rows, scan_max=None):
        x, y, z = pos
        self.evidence = {
            'pos': list(pos), 'expected_block': block_id,
            'observed_state': observed_state or None,
            'scan': {'min': list(pos), 'max': list(scan_max) if scan_max is not None else [x, y + 6, z],
                     'blocks': [{'pos': row.get('pos'), 'state': row.get('state')}
                                for row in rows]},
        }
        super().__init__('Expected outdoor chest changed')


def verify_opened_chest(client, source):
    """Recheck the exact block before trusting an open menu or transfer."""
    if source is None:
        return  # Offline clients may replace the opener with a menu fixture.
    pos, expected = source['pos'], source['state']
    rows = client.request('scan', min=pos, max=pos, details=True)['blocks']
    observed = next((r['state'] for r in rows if r['pos'] == pos), '')
    if observed != expected:
        raise OutdoorChestChanged(pos, 'minecraft:chest', observed, rows, scan_max=pos)


def open_grounded_chest(client, pos, block_id='minecraft:chest', *, allow_empty=False):
    if block_id not in ('minecraft:chest','minecraft:ender_chest'):
        raise ValueError('Only ordinary or Ender chests use this landing approach')
    x,y,z=pos
    rows=client.request('scan',min=pos,max=[x,y+6,z],details=True)['blocks']
    expected=next((r['state'] for r in rows if r['pos']==pos),'')
    if not expected.startswith('Block{'+block_id+'}'):
        raise OutdoorChestChanged(pos, block_id, expected, rows)
    if any(r['pos'][1]>y and r['state']!='Block{minecraft:air}' for r in rows):
        raise RuntimeError('Chest landing column is obstructed')
    hand=select_container_hand(client)
    state=client.status();point=state.get('pos');lease=state.get('supervision_lease')or{}
    if (state.get('air_only_navigation_protocol',0)>=2 and lease.get('kind')=='materials'
            and lease.get('job_session')==getattr(client,'task',None)
            and lease.get('world_session')==getattr(client,'world',None)
            and isinstance(point,list)and len(point)==3 and point[1]>y+4):
        # The precise native air navigator verifies the entire body sweep.
        # Descend above the known chest before the short-range supply planner,
        # which otherwise has to traverse many vertical grid nodes at cruise height.
        from material_jobs.navigation import settled_state
        above=[x+.5,point[1],z+.5];near=[x+.5,y+1.8,z+.5]
        client.checked('navigate',target=above,arrival=.15,air_only=True,seconds=45)
        client.checked('navigate',target=near,arrival=.15,air_only=True,seconds=45)
        settled_state(client,near,.4)
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
    client.checked('interact',pos=pos,face='up',expected_state=expected,expected_hand=hand)
    state = wait_container_contents(client,'ChestMenu',require_nonempty=not allow_empty)
    from material_storage_index import bind_source
    bind_source(client,state,pos,block_id)
    return {**state, '_verified_chest': {'pos': list(pos), 'state': expected}}


def open_chest_from_pose(client,pos,pose,face,*,allow_empty=False):
    """Open a registered indoor chest after the existing route reached its pose.

    This function never finds a route, descends onto a roof, or moves the player.
    The caller must supply an explicit registered stand and a side face.
    """
    if (not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos)
            or not isinstance(pose,list)or len(pose)!=3
            or any(type(v)not in(int,float)or not math.isfinite(v)for v in pose)
            or face not in('north','south','west','east')):
        raise ValueError('Indoor chest needs an exact position, registered stand and side face')
    def settled():
        until=time.monotonic()+4
        while True:
            s=client.status();lease=s.get('supervision_lease')or{};point=s.get('pos');velocity=s.get('velocity')
            menu=s.get('menu')or{}
            invalid=(s.get('connected')is not True or s.get('world_session')!=client.world
                or s.get('control_revision')!=client.rev or lease.get('kind')!='materials'
                or lease.get('world_session')!=client.world or lease.get('job_session')!=client.task
                or lease.get('revision')!=client.rev
                or not isinstance(point,list)or len(point)!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in point)or math.dist(point,pose)>.55
                or not isinstance(velocity,list)or len(velocity)!=3
                or any(type(v)not in(int,float)or not math.isfinite(v)for v in velocity)
                or s.get('flight')is not False
                or s.get('under_water')is not False or s.get('manual_movement')is not False
                or s.get('screen')!=''or s.get('health',0)<19 or s.get('guard_busy')is not False
                or s.get('guard_armed')is not True or s.get('guard_pve_only')is not True
                or menu.get('type')!='InventoryMenu'or menu.get('id')!=0 or menu.get('cursor',{}).get('count')!=0)
            stable=not invalid and s.get('on_ground')is True and math.hypot(velocity[0],velocity[2])<.03
            if stable:return s
            if invalid or time.monotonic()>=until:
                out=getattr(client,'out',None)
                if isinstance(out,(str,Path)):
                    (Path(out)/'indoor-stand-refusal.json').write_text(json.dumps({'pose':pose,'pos':pos,
                        'state':{k:s.get(k)for k in('time','pos','velocity','on_ground','flight','screen','world_session',
                            'control_revision','health','guard_busy','guard_armed','guard_pve_only','under_water','manual_movement','supervision_lease')},
                        'menu':{k:menu.get(k)for k in('id','type','cursor')},'interaction_sent':False},ensure_ascii=False,indent=2)+'\n')
                raise RuntimeError('Indoor chest registered grounded pose or controller changed; no interaction')
            client.request('snapshot');time.sleep(.15)
    settled()
    reply=client.request('scan',min=pos,max=pos,details=True)
    if (reply.get('phase')!='done'or reply.get('world_session')!=client.world
            or reply.get('scan_cells_read')!=1 or reply.get('scan_total_cells')!=1
            or any(type(reply.get(k))is not int or reply[k]!=client.rev
                   for k in('control_revision','scan_start_revision','scan_end_revision'))
            or not isinstance(reply.get('blocks'),list)or len(reply['blocks'])!=1):
        raise RuntimeError('Indoor chest scan is incomplete; no interaction')
    row=reply['blocks'][0];expected=row.get('state','')
    if row.get('pos')!=pos or not expected.startswith('Block{minecraft:chest}'):
        raise OutdoorChestChanged(pos,'minecraft:chest',expected,reply['blocks'],scan_max=pos)
    if row.get('fluid')is not False:
        raise RuntimeError('Indoor chest has unverified fluid; no interaction')
    settled();hand=select_container_hand(client);settled()
    client.checked('interact',pos=pos,face=face,expected_state=expected,expected_hand=hand)
    state=wait_container_contents(client,'ChestMenu',require_nonempty=not allow_empty)
    source={'pos':list(pos),'state':expected};verify_opened_chest(client,source)
    from material_storage_index import bind_source
    bind_source(client,state,pos,'minecraft:chest')
    return {**state,'_verified_chest':source}


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
