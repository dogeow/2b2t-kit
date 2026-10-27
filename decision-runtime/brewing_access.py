"""Open an exact already-reached brewing stand; never move or adopt a foreign menu."""
import math
from container_hand import select_container_hand
from container_access import wait_container_contents

def admitted(state,world,task,revision,pose):
    try:
        menu=state['menu'];lease=state['supervision_lease']
        return(state['connected']is True and state['world_session']==world and state['control_revision']==revision
          and lease['kind']=='materials'and lease['job_session']==task and lease['world_session']==world and lease['revision']==revision
          and state['health']==20 and state['manual_movement']is False and state['screen']==''
          and menu['type']=='InventoryMenu'and menu['id']==0 and menu['cursor']['count']==0
          and len(pose)==3 and all(type(v)in(int,float)and math.isfinite(v)for v in pose)
          and math.dist(state['pos'],pose)<.2 and math.hypot(state['velocity'][0],state['velocity'][2])<.04
          and abs(state['velocity'][1])<.1 and(state.get('on_ground')is True or state.get('flight')is True and state.get('air_only_navigation_protocol',0)>=2)
          and state['guard_armed']is True and state['guard_pve_only']is True and state['under_water']is False)
    except(KeyError,ValueError,TypeError):return False

def open_registered(client,pos,pose,face):
    if(not isinstance(pos,list)or len(pos)!=3 or any(type(v)is not int for v in pos)
       or face not in('up','north','south','west','east')):raise ValueError('Exact brewing stand position and face required')
    if not admitted(client.status(),client.world,client.task,client.rev,pose):raise RuntimeError('Brewing stand pose or native owner changed; no input')
    scan=client.request('scan',min=pos,max=pos,details=True)
    if(scan.get('phase')!='done'or scan.get('scan_total_cells')!=1 or scan.get('scan_cells_read')!=1
       or scan.get('world_session')!=client.world or scan.get('scan_start_revision')!=client.rev
       or scan.get('scan_end_revision')!=client.rev or len(scan.get('blocks',[]))!=1):raise RuntimeError('Brewing stand scan incomplete; no interaction')
    row=scan['blocks'][0]
    if row.get('pos')!=pos or not row.get('state','').startswith('Block{minecraft:brewing_stand}')or row.get('fluid')is not False:raise RuntimeError('Registered brewing stand changed; no interaction')
    hand=select_container_hand(client)
    if not admitted(client.status(),client.world,client.task,client.rev,pose):raise RuntimeError('Brewing stand pose changed before interaction')
    client.checked('interact',pos=pos,face=face,expected_state=row['state'],expected_hand=hand)
    return wait_container_contents(client,'BrewingStandMenu',require_nonempty=False)
