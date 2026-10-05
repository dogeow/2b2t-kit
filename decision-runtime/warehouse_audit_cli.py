"""Inspect explicitly requested island storage using one guarded Kit client.

Inventory is read through real block scans and two stable menu frames. This
module never clicks inventory slots, transfers items or places/unpacks boxes.
"""
from copy import deepcopy
from collections import Counter
import argparse
import json
import math
from pathlib import Path
import re
import time

from kit_runtime.journal import write_json
from live_snapshot import read_fresh
from material_client import Client, MaterialClient
from material_jobs.profile import profile_path
from material_jobs.protocol import server_key
from safety_interlock import require_unlocked

DEFAULT_GAME=Path('/Applications/.minecraft/versions/26.1.2')
ALLOWED=frozenset(('scan','snapshot','navigate','walk','approach_block','select_item',
                   'interact','close_menu','material_job_park'))
ITEM=re.compile(r'[a-z0-9_.-]+:[a-z0-9_./-]+')
MENU_LAYOUTS={'minecraft:chest':('ChestMenu',27),'minecraft:ender_chest':('ChestMenu',27),
              'minecraft:barrel':('ChestMenu',27),'minecraft:hopper':('HopperMenu',5),
              'minecraft:blast_furnace':('BlastFurnaceMenu',3)}
READ_TERMINALS=frozenset(('scan','snapshot','navigate','walk','approach_block','select_item','close_menu'))


class StockBlocked(RuntimeError):
    pass


def _depots(values):
    if not isinstance(values,(tuple,list)) or not 1<=len(values)<=64:
        raise ValueError('Supply 1..64 explicit storage coordinates')
    result=[]
    for pos in values:
        if (not isinstance(pos,(tuple,list)) or len(pos)!=3 or any(type(v)is not int for v in pos)
                or not -64<=pos[1]<=319 or any(abs(pos[i])>29_999_984 for i in (0,2))):
            raise ValueError('Storage coordinates must be legal integer XYZ positions')
        if list(pos) not in result:result.append(list(pos))
    return result


def _inventory(state):
    rows=[row for row in state.get('inventory',[]) if type(row.get('slot'))is int and 0<=row['slot']<36]
    if len(rows)!=36 or {row['slot'] for row in rows}!=set(range(36)):
        raise StockBlocked('Exact main inventory is unavailable')
    return sorted(deepcopy(rows),key=lambda row:row['slot'])


def _identity(state):
    return {key:deepcopy(state.get(key)) for key in
            ('world_session','player_uuid','projection_selection','dimension')} | {'server':server_key(state.get('server'))}


def _check(state,initial):
    if (state.get('connected')is not True or state.get('manual_movement')
            or _identity(state)!=_identity(initial) or state.get('health',0)<19 or state.get('food',0)<18
            or state.get('under_water') or not state.get('guard_armed') or not state.get('guard_pve_only')
            or (state.get('safety_hold')or{}).get('active')
            or state.get('recent_hurt_at',0)>initial.get('recent_hurt_at',0)):
        raise StockBlocked('World, player, projection, health or manual control changed')
    if _inventory(state)!=_inventory(initial):
        raise StockBlocked('Main inventory changed during read-only storage inspection')
    return state


def _scan(client,low,high):
    reply=client.request('scan',min=list(low),max=list(high),details=True)
    total=math.prod(b-a+1 for a,b in zip(low,high))
    revision=getattr(client,'rev',None)
    if (reply.get('phase')!='done' or reply.get('world_session')!=client.world
            or reply.get('scan_cells_read')!=total or reply.get('scan_total_cells')!=total
            or any(type(reply.get(key))is not int for key in
                   ('control_revision','scan_start_revision','scan_end_revision','scan_cells_read','scan_total_cells'))
            or type(revision)is not int or any(reply.get(key)!=revision for key in
                                              ('control_revision','scan_start_revision','scan_end_revision'))
            or not isinstance(reply.get('blocks'),list)):
        raise StockBlocked('Complete current server block scan is unavailable')
    seen=set()
    for row in reply['blocks']:
        pos=row.get('pos') if isinstance(row,dict) else None
        if (not isinstance(pos,list) or len(pos)!=3 or any(type(v)is not int for v in pos)
                or tuple(pos)in seen or any(not low[i]<=pos[i]<=high[i] for i in range(3))
                or not isinstance(row.get('state'),str)):
            raise StockBlocked('Malformed current storage block evidence')
        seen.add(tuple(pos))
    return reply


def _state_parts(value):
    matched=re.fullmatch(r'Block\{([^}]+)\}(?:\[([^]]*)\])?',value or '')
    if not matched:raise StockBlocked('Exact container block state is unavailable')
    properties=dict(part.split('=',1) for part in (matched[2]or'').split(',') if '='in part)
    return matched[1],properties


def _ground_reach_profile(profile):
    """A declared seven-barrel row uses the existing floor, never an attic."""
    value=profile.get('ground_reach_storage')
    if value is None:return None
    allowed={'schema','expected_block','foot_y','sources','stances'}
    if (not isinstance(value,dict)or set(value)!=allowed or type(value.get('schema'))is not int or value['schema']!=1
            or value.get('expected_block')!='minecraft:barrel' or type(value.get('foot_y'))is not int
            or not -64<=value['foot_y']<=315):
        raise StockBlocked('Ground-reach profile requires the explicit supported barrel/floor schema')
    sources=value.get('sources');stances=value.get('stances');foot=value['foot_y']
    if not isinstance(sources,list)or len(sources)!=7 or len(_depots(sources))!=7:
        raise StockBlocked('Ground reach needs seven unique legal source cells')
    sources=sorted(sources,key=lambda p:p[2]);x,y,z=sources[0]
    if sources!=[[x,foot+4,z+i]for i in range(7)]:
        raise StockBlocked('Ground reach supports only a declared seven-cell barrel row four blocks above its floor')
    for name in ('workbench_entry','workbench_exit'):
        route=profile.get(name)
        if not isinstance(route,list)or not route:
            raise StockBlocked('Ground-reach storage needs both existing registered door routes')
        walks=[]
        for step in route:
            if not isinstance(step,dict)or step.get('kind')not in ('walk','door'):
                raise StockBlocked('Ground reach cannot introduce a ladder, platform or unknown route step')
            if step['kind']=='walk':
                target=step.get('target')
                if (not isinstance(target,list)or len(target)!=3
                        or any(type(v)not in(int,float)or not math.isfinite(v)for v in target)or target[1]!=foot
                        or any(abs(target[i])>29_999_984 for i in (0,2))):
                    raise StockBlocked('Ground-reach entry and exit must retain the declared actual foot level')
                walks.append(target)
        if not walks:raise StockBlocked('Ground reach needs an actual registered floor walk')
    expected=[{'pos':[x-1.5,foot,z+offset+.5],'face':'west'}for offset in (2,3,4)]
    if (not isinstance(stances,list)or len(stances)!=3
            or any(not isinstance(s,dict)or set(s)!={'pos','face'}for s in stances)
            or any(not isinstance(s['pos'],list)or len(s['pos'])!=3
                   or any(type(v)not in(int,float)or not math.isfinite(v)for v in s['pos'])
                   or any(abs(s['pos'][i])>29_999_984 for i in (0,2))for s in stances)
            or stances!=expected):
        raise StockBlocked('Ground reach requires the three explicit reversible west aisle stances on the original floor')
    return {**deepcopy(value),'sources':sources}


def _ground_reach(profile,pos,block_state):
    value=_ground_reach_profile(profile)
    if value is None or pos not in value['sources']:return None
    if _state_parts(block_state)[0]!=value['expected_block']:
        raise StockBlocked('Declared reachable barrel changed; no alternate container is authorized')
    return value


def _ray_cell(start,end,pos):
    """Voxel intersection of rays from any eye within the normal player body."""
    lower,upper=0.0,1.0
    for axis in (0,2):
        delta=end[axis]-start[axis]
        if abs(delta)<1e-12:
            if not pos[axis]<=start[axis]<=pos[axis]+1:return False
            continue
        a,b=(pos[axis]-start[axis])/delta,(pos[axis]+1-start[axis])/delta
        lower=max(lower,min(a,b));upper=min(upper,max(a,b))
        if lower>upper:return False
    # This broad body-to-face envelope is a filter, not an inferred eye pose.
    ys=[start[1]+height+(end[1]-start[1]-height)*t for height in (0,1.8)for t in (lower,upper)]
    return max(ys)>=pos[1]and min(ys)<pos[1]+1


def _ground_reach_ray(session,pos,block_state,stance):
    before=session.status();point=before['pos'];initial=session.initial
    _check(before,initial)
    if (math.dist(point,stance)>.55 or before.get('manual_movement')is not False
            or before.get('screen') or before.get('navigating')or before.get('native_material_busy')or before.get('guard_busy')):
        raise StockBlocked('Actual ground-reach stance is not idle and stable')
    _body_clearance(session)
    aim=[pos[0]+1e-5,pos[1]+.5,pos[2]+.5]
    low=[math.floor(min(point[i],aim[i]))for i in range(3)]
    high=[math.floor(max(point[i]+(1.8 if i==1 else 0),aim[i]))for i in range(3)]
    reply=_scan(session,low,high)
    target=None
    for row in reply['blocks']:
        if row['pos']==pos:
            target=row
            if row['state']!=block_state or row.get('fluid')is not False:
                raise StockBlocked('Ground-reach target changed before native pre-use validation')
        elif _ray_cell(point,aim,row['pos']):
            if (row['state']!='Block{minecraft:air}'or row.get('fluid')is not False
                    or row.get('passable')is not True or row.get('block_entity')is not False):
                raise StockBlocked('Current conservative ground-reach ray envelope is occupied or unknown; no interaction')
    if target is None:raise StockBlocked('Ground-reach ray lacks the exact current barrel')
    after=session.status();_check(after,initial)
    if math.dist(after['pos'],point)>.05:
        raise StockBlocked('Actual ground-reach pose changed during the ray scan')
    proof={'source':list(pos),'stance':list(point),'requested_face':'west','scan_request_id':reply.get('id'),
           'scan_min':low,'scan_max':high,'scan_ended_at':reply.get('scan_ended_at'),
           'ray_scope':'conservative_normal_player_body_to_barrel_face_voxels',
           'eye_position_verified':False,'current_interaction_range_verified':False,'actual_used_face_verified':False,
           'native_pre_use_required':'actual_eye_and_synced_range_outline_before_and_after_rotation'}
    session.report.setdefault('ground_reach_proofs',[]).append(proof);session.save()
    return proof


def _container(session,pos):
    reply=_scan(session,pos,pos);row=next((v for v in reply['blocks']if v['pos']==pos),None)
    if row is None:raise StockBlocked('Requested storage block is absent; no interaction sent')
    name,props=_state_parts(row['state'])
    if name not in MENU_LAYOUTS:
        raise StockBlocked('Requested block has no explicitly supported read-only storage menu')
    positions=[list(pos)]
    if name=='minecraft:chest' and props.get('type')in ('left','right'):
        direction={'north':(1,0),'east':(0,1),'south':(-1,0),'west':(0,-1)}.get(props.get('facing'))
        if direction is None:raise StockBlocked('Double-chest facing is unavailable')
        sign=1 if props['type']=='left' else -1
        other=[pos[0]+direction[0]*sign,pos[1],pos[2]+direction[1]*sign]
        partner=_scan(session,other,other)
        found=next((v for v in partner['blocks']if v['pos']==other),None)
        partner_name,partner_props=_state_parts(found['state']if found else '')
        if (partner_name!=name or partner_props.get('facing')!=props.get('facing')
                or partner_props.get('type')!=('right'if props['type']=='left'else'left')):
            raise StockBlocked('Current double-chest partner is unconfirmed')
        positions.append(other)
    key=('ender:'+session.initial['player_uuid'] if name=='minecraft:ender_chest' else
         name.removeprefix('minecraft:')+':'+json.dumps(sorted(positions),separators=(',',':')))
    return key,row['state'],positions


def _travel_to(client,pos,checkpoint,trace):
    from material_jobs.acquisition import _travel
    state=client.status()
    if state.get('flight')is not True:
        column=_scan(client,[math.floor(state['pos'][0]-.35),-64,math.floor(state['pos'][2]-.35)],
                     [math.floor(state['pos'][0]+.35),319,math.floor(state['pos'][2]+.35)])
        ground=max((r['pos'][1]+1 for r in column['blocks']if r.get('fluid')or not r.get('passable',False)),default=None)
        if ground is None or ground+24>315:raise StockBlocked('No loaded safe ascent after leaving storage')
        client.core.park_target=[state['pos'][0],max(state['pos'][1],ground+24),state['pos'][2]]
        _follow_clear_points(client,[client.core.park_target])
        state=client.status()
    target=[pos[0]+.5,max(state['pos'][1],min(315,pos[1]+24)),pos[2]+.5]
    _travel(client,target,checkpoint,trace,keep_cruise=True)


class _RegisteredRoute:
    """Reuse existing verified door/walk implementations without another backend."""
    def __init__(self,session,profile):self.session,self.profile=session,profile
    def ensure_client(self):return self.session
    def checkpoint(self):self.session.status()
    def route(self,name):
        from material_jobs_backend import Backend
        return Backend.route(self,name)
    def approach_route_entry(self,target):
        from material_jobs_backend import Backend
        return Backend.approach_route_entry(self,target)
    def route_door(self,c,step):
        from material_jobs_backend import Backend
        return Backend.route_door(self,c,step)


def _open_container(session,pos,block_state,profile):
    from container_access import open_grounded_chest,wait_container_contents
    name,_=_state_parts(block_state)
    ground_reach=_ground_reach(profile,pos,block_state)
    column=_scan(session,pos,[pos[0],min(319,pos[1]+6),pos[2]])
    overhead=any(v['pos'][1]>pos[1] for v in column['blocks'])
    if name in ('minecraft:chest','minecraft:ender_chest') and any(
            v['pos']==[pos[0],pos[1]+1,pos[2]] and v.get('solid')is True for v in column['blocks']):
        raise StockBlocked('Chest lid is covered by a full collision block; preserve the cover')
    if not overhead and name in ('minecraft:chest','minecraft:ender_chest'):
        return open_grounded_chest(session,pos,name,allow_empty=True)
    workbench=profile.get('workbench')
    house=((overhead or ground_reach is not None) and profile.get('workbench_entry') and profile.get('workbench_exit') and workbench
           and math.dist(pos,workbench)<=16)
    foliage_only=overhead and all(_state_parts(v['state'])[0].endswith('_leaves')
                                and v.get('fluid')is False
                                for v in column['blocks']if v['pos'][1]>pos[1])
    if overhead and not house and not foliage_only and name in ('minecraft:chest','minecraft:ender_chest','minecraft:barrel'):
        raise StockBlocked('Roofed storage needs a local registered house entry route; preserve the structure')
    # Overhead foliage is not evidence that the actor must enter a house.
    # The existing side-access kernel proves a dry, finite body/entity sweep
    # and its reverse before moving; blocked columns still remain outside.
    route=_RegisteredRoute(session,profile)
    if house and not session.in_house:
        exit_walks=[step.get('target')for step in profile['workbench_exit']if step.get('kind')=='walk']
        if not exit_walks or ground_reach is None and abs(pos[1]-exit_walks[0][1])>2:
            raise StockBlocked('High house storage has no registered same-level return to the door exit')
        staging=profile.get('workbench_staging')
        if staging:
            from material_jobs.acquisition import _travel
            _travel(session,staging,session.status,[],keep_cruise=True)
        session.in_house=True
        route.route('workbench_entry')
    face=_side_access(session,pos,block_state,house=bool(house),profile=profile)
    session.checked('select_item',item='minecraft:diamond_sword')
    if ground_reach is not None:
        _ground_reach_ray(session,pos,block_state,session.report['storage_return']['stance'])
    session.checked('interact',pos=pos,face=face,expected_state=block_state,expected_hand='minecraft:diamond_sword')
    return wait_container_contents(session,MENU_LAYOUTS[name][0],require_nonempty=False)


def _clear_sweep(session,start,end):
    from material_jobs.navigation import _body_sweep
    from potato_farm import valid_entity_scope
    low,high=_body_sweep(start,end)
    if math.prod(b-a+1 for a,b in zip(low,high))>8192:
        raise StockBlocked('Storage return body corridor exceeds its bounded proof')
    reply=_scan(session,low,high)
    if not valid_entity_scope(reply.get('scan_entity_scope')) or not isinstance(reply.get('scan_entities'),list):
        raise StockBlocked('Storage return body entity scope is unavailable')
    if any(not isinstance(e,dict)or e.get('type')not in ('minecraft:item','minecraft:experience_orb')
           or e.get('hostile')is not False for e in reply['scan_entities']):return False
    safe={'minecraft:torch','minecraft:wall_torch','minecraft:short_grass','minecraft:tall_grass',
          'minecraft:fern','minecraft:large_fern'}
    def clear(row):
        name=_state_parts(row['state'])[0]
        if name in safe and row.get('passable')is True and row.get('fluid')is False and row.get('block_entity')is False:return True
        return (name in ('minecraft:chest','minecraft:ender_chest')and row.get('solid')is False
                and row.get('fluid')is False and row['pos'][1]+14/16<=min(start[1],end[1])+1e-6)
    return all(clear(row)for row in reply['blocks'])


def _follow_clear_points(session,points):
    from material_jobs.acquisition import _actual_route_steps
    from material_jobs.navigation import settled_state
    for before,target in _actual_route_steps(session,points,session.status,None):
        if not _clear_sweep(session,before['pos'],target):
            raise StockBlocked('Original storage return body corridor changed; no movement sent')
        session.checked('navigate',target=target,arrival=.25,seconds=90,air_only=True)
        current=settled_state(session,target,.55)
        if math.dist(current['pos'],target)>.55:
            raise StockBlocked('Original storage corridor endpoint was not confirmed')


def _side_access(session,pos,block_state,*,house=False,profile=None):
    """Select an exact stance only after proving its finite reversible corridor."""
    before=session.status();origin=list(before['pos'])
    if (math.hypot(origin[0]-pos[0]-.5,origin[2]-pos[2]-.5)>16
            or not house and before.get('flight')is not True):
        raise StockBlocked('Storage side access needs the nearby verified guarded start')
    foot_y=origin[1]if house else pos[1]+.02
    ground_reach=_ground_reach(profile or{},pos,block_state)if house else None
    if ground_reach is not None and abs(foot_y-ground_reach['foot_y'])>.55:
        raise StockBlocked('Actual house foot pose differs from the declared existing floor')
    if house and ground_reach is None and abs(pos[1]-foot_y)>2:
        raise StockBlocked('High house storage lacks a same-level registered return corridor')
    candidates=[(face,[pos[0]+.5+dx*distance,foot_y,pos[2]+.5+dz*distance])
                for distance in (1,2)for face,dx,dz in
                (('west',-1,0),('north',0,-1),('south',0,1),('east',1,0))]
    if ground_reach is not None:
        candidates=[(s['face'],s['pos'])for s in sorted(ground_reach['stances'],key=lambda s:math.dist(s['pos'],[pos[0],foot_y,pos[2]+.5]))]
    for face,stance in candidates:
        bend=[stance[0],origin[1],origin[2]if house else stance[2]]
        if not (_clear_sweep(session,origin,bend)and _clear_sweep(session,bend,stance)):continue
        if math.dist(session.status()['pos'],origin)>.05:
            raise StockBlocked('Storage start moved while proving its original return')
        session.return_points=[bend,origin]
        session.report['storage_return']={'world_session':session.world,'origin':origin,'stance':stance,
                                         'points':deepcopy(session.return_points),'house':house,'state':'proved_before_entry'}
        session.save()
        _follow_clear_points(session,[bend,stance])
        if ground_reach is not None:
            _ground_reach_ray(session,pos,block_state,stance)
        return face
    raise StockBlocked('No finite reversible storage side corridor; remain outside')


def _exit_storage(session,profile):
    if session.report.get('pending'):
        raise StockBlocked('Original native operation remains unresolved; no exit or finish')
    state=session.status();menu=state.get('menu')or{}
    if state.get('screen'):
        if (menu.get('id')!=session.owned_material_menu or menu.get('type')not in
                {value[0]for value in MENU_LAYOUTS.values()}or(menu.get('cursor')or{}).get('count')!=0):
            raise StockBlocked('Unowned or occupied storage menu prevents automatic exit')
        session.checked('close_menu')
    if session.return_points:
        _follow_clear_points(session,session.return_points)
        session.return_points=[]
        session.report['storage_return']['state']='returned_to_original_verified_start';session.save()
    if session.in_house:
        _RegisteredRoute(session,profile).route('workbench_exit');session.in_house=False
        session.report['house_exit']='original_registered_exit_completed';session.save()


def _same_opened_state(before,after):
    """An owned barrel menu changes only its OPEN animation, never its identity."""
    name,old=_state_parts(before);current,new=_state_parts(after)
    if name!=current:return False
    if name!='minecraft:barrel':return before==after
    if old.get('open')not in ('false','true')or new.get('open')not in ('false','true'):return False
    return {k:v for k,v in old.items()if k!='open'}=={k:v for k,v in new.items()if k!='open'}


def _body_clearance(session):
    """Recheck the reached pose, never infer attic access from a ground entry."""
    from potato_farm import valid_entity_scope
    before=session.status();pos=before.get('pos')
    if (not isinstance(pos,list) or len(pos)!=3
            or any(type(v)not in (int,float)or not math.isfinite(v)for v in pos)):
        raise StockBlocked('Actual reached body pose is unavailable')
    low=[math.floor(pos[0]-.3+1e-6),math.floor(pos[1]+1e-6),math.floor(pos[2]-.3+1e-6)]
    high=[math.floor(pos[0]+.3-1e-6),math.floor(pos[1]+1.8-1e-6),math.floor(pos[2]+.3-1e-6)]
    reply=_scan(session,low,high)
    if not valid_entity_scope(reply.get('scan_entity_scope')) or not isinstance(reply.get('scan_entities'),list):
        raise StockBlocked('Current reached body entity evidence is unavailable')
    for entity in reply['scan_entities']:
        if (not isinstance(entity,dict) or entity.get('type')not in ('minecraft:item','minecraft:experience_orb')
                or entity.get('hostile')is not False):
            raise StockBlocked('A current entity intersects the reached storage body space')
    for row in reply['blocks']:
        if row.get('fluid')is False and row.get('passable')is True:continue
        name,_=_state_parts(row['state'])
        # An outdoor chest landing stands on its 14/16-height collision shape.
        if (name in ('minecraft:chest','minecraft:ender_chest') and row.get('solid')is False
                and row.get('fluid')is False and row['pos'][1]+14/16<=pos[1]+1e-6):continue
        raise StockBlocked('Current reached storage body space is obstructed')
    after=session.status()
    if math.dist(pos,after['pos'])>.05:
        raise StockBlocked('The reached storage pose changed during its body scan')
    return {'pos':pos,'min':low,'max':high,'scan_request_id':reply.get('id'),
            'scan_ended_at':reply.get('scan_ended_at'),'entity_scope':reply['scan_entity_scope']}


class _Session:
    def __init__(self,client,initial,report,out):
        self.core,self.initial,self.report,self.out=client,initial,report,Path(out)
        self.sequence=0;self.in_house=False;self.return_points=[]
    def __getattr__(self,key):return getattr(self.core,key)
    @property
    def owned_material_menu(self):return self.core.owned_material_menu
    @owned_material_menu.setter
    def owned_material_menu(self,value):self.core.owned_material_menu=value
    def save(self):write_json(self.out/'stock-audit.json',self.report)
    def status(self,*args,**kwargs):return _check(self.core.status(*args,**kwargs),self.initial)
    def request(self,op,**params):
        if op not in ALLOWED:raise StockBlocked('Storage audit forbids inventory mutation or placement')
        if self.report.get('pending'):raise StockBlocked('Original native operation remains unresolved; no new request')
        self.status();self.sequence+=1
        self.report['pending']={'sequence':self.sequence,'op':op,'params':deepcopy(params),
                               'world_session':self.world,'task_session':self.task,'request_before':self.core.last}
        self.save()
        try:
            reply=self.core.request(op,**params)
        except Exception:
            self.report['pending'].update(request_id=self.core.last,native_inflight=deepcopy(self.core.native_inflight))
            if self.core.last==self.report['pending']['request_before'] and self.core.native_inflight is None:
                try:
                    current=self.status();lease=current.get('supervision_lease')or{}
                    if (not current.get('navigating')and not current.get('native_material_busy')
                            and lease.get('kind')=='materials'and lease.get('id')==self.core.heartbeat.id
                            and lease.get('job_session')==self.task and lease.get('world_session')==self.world
                            and lease.get('revision')==self.rev):
                        self.report.setdefault('known_local_preflights',[]).append({'op':op,'request_dispatched':False})
                        self.report['pending']=None
                except Exception:pass
            self.save();raise
        write_json(self.out/'receipts'/('%06d-%s.json'%(self.sequence,op)),reply)
        current=self.status()
        if reply.get('phase')not in (None,'done'):
            lease=current.get('supervision_lease')or{}
            before_use=(op=='interact'and params.get('expected_hand')=='minecraft:diamond_sword'
                        and reply.get('phase')=='error'and reply.get('detail')in
                        ('Target block changed','Held item changed','Target interaction face is occluded or out of reach'))
            terminal=((op in READ_TERMINALS or before_use)and reply.get('phase')in ('error','waiting','stopped')
                and reply.get('id')==self.core.last and isinstance(self.core.last,str)
                and reply.get('world_session')==self.world and type(reply.get('control_revision'))is int
                and reply['control_revision']==self.rev and type(current.get('control_revision'))is int
                and current.get('last_request')==self.core.last and current.get('control_revision')==self.rev
                and not current.get('navigating')and not current.get('native_material_busy')
                and self.core.native_inflight is None and lease.get('kind')=='materials'
                and lease.get('id')==self.core.heartbeat.id and lease.get('job_session')==self.task
                and lease.get('world_session')==self.world and lease.get('revision')==self.rev)
            if terminal:
                self.report.setdefault('known_read_terminals',[]).append({'request_id':self.core.last,'op':op,
                    'phase':reply['phase'],'world_session':self.world,'control_revision':self.rev})
                self.report['pending']=None;self.save();return reply
            self.report['pending'].update(request_id=self.core.last,terminal_phase=reply.get('phase'))
            self.save();raise StockBlocked('Original native operation was not confirmed; no replay')
        self.report['pending']=None;self.save()
        return reply
    def checked(self,op,**params):
        reply=self.request(op,**params)
        if reply.get('phase')!='done':raise StockBlocked(reply.get('detail','Native operation lacks a done receipt'))
        return reply
    def transfer(self,*args,**kwargs):raise StockBlocked('Storage audit cannot transfer inventory')


def _menu_signature(state,expected_slots,expected_kind='ChestMenu'):
    menu=state.get('menu')or{};rows=menu.get('slots')
    if (menu.get('type')!=expected_kind or type(menu.get('id'))is not int
            or not isinstance(rows,list) or len(rows)!=expected_slots+36
            or (menu.get('cursor')or{}).get('count')!=0):
        raise StockBlocked('Actual storage menu, slot coverage or cursor is unconfirmed')
    if {row.get('slot')for row in rows}!=set(range(len(rows))):
        raise StockBlocked('Actual menu slots are duplicated or incomplete')
    for row in rows:
        if (not isinstance(row.get('item'),str) or ITEM.fullmatch(row['item'])is None
                or type(row.get('count'))is not int or row['count']<0):
            raise StockBlocked('Actual menu item counts are unavailable')
    return json.dumps(menu,sort_keys=True,separators=(',',':'))


def _read_menu(session,expected_slots,sleeper,menu_id=None,expected_kind='ChestMenu'):
    deadline=time.monotonic()+20;previous=None;last_time=None
    while time.monotonic()<deadline:
        state=session.request('snapshot');_check(state,session.initial)
        if menu_id is not None and state.get('menu',{}).get('id')!=menu_id:
            session.report['pending']={'op':'menu_scope_changed','original_menu_id':menu_id,
                                       'request_id':session.core.last}
            session.save();raise StockBlocked('The originally opened container menu changed; preserve user control')
        signature=_menu_signature(state,expected_slots,expected_kind);stamp=state.get('time')
        if type(stamp)is not int:raise StockBlocked('Menu observation time is unavailable')
        if signature==previous and last_time is not None and stamp>last_time:return state
        previous,last_time=signature,stamp;sleeper(.25)
    raise StockBlocked('Two distinct stable storage menu frames were not observed')


def _contents(rows):
    loose,packed=Counter(),Counter();unknown=[]
    for row in rows:
        if row['count']:loose[row['item']]+=row['count']
        if row['count']==1 and row['item'].endswith('shulker_box'):
            children=row.get('contains')
            if not isinstance(children,list):unknown.append(row['slot']);continue
            for child in children:
                if (not isinstance(child,dict) or not isinstance(child.get('item'),str)
                        or ITEM.fullmatch(child['item'])is None or type(child.get('count'))is not int or child['count']<0):
                    raise StockBlocked('Provided packed-container metadata is incomplete')
                packed[child['item']]+=child['count']
    return dict(loose),dict(packed),unknown


def _finish_proof(client,initial):
    worker=json.loads((client.out/'stock-safety.json').read_text())
    native=json.loads((client.root/('supervision-receipt-'+client.heartbeat.id+'.json')).read_text())
    frame=worker.get('parking_confirmation');current=_check(client.raw(),initial)
    if (worker.get('native_receipt')is not True or not isinstance(frame,dict)
            or any(worker.get(k)!=native.get(k)for k in ('lease','job_session','action','time'))
            or native.get('lease')!=client.heartbeat.id or native.get('job_session')!=client.task
            or native.get('action')!='KEEP_PVE_GUARD' or type(native.get('time'))is not int or native['time']<=0
            or not isinstance(native.get('snapshot'),dict) or native['snapshot'].get('world_session')!=client.world
            or not isinstance(worker.get('snapshot'),dict) or worker['snapshot'].get('world_session')!=client.world
            or worker.get('local_verified') or native.get('local_verified')
            or worker.get('lease_transition_pending') or native.get('lease_transition_pending')
            or frame.get('time',0)<native['time'] or current.get('time',0)<frame.get('time',0)
            or frame.get('control_revision')!=client.rev or current.get('control_revision')!=client.rev
            or not client._owned_guarded_finish_state(frame,'parking') or not client.park_near(frame)
            or not client._owned_guarded_finish_state(current,'parking') or not client.park_near(current)):
        raise StockBlocked('Exact original native parking receipt and current protection are unconfirmed')
    return {'native_receipt':native,'current_parking':current}


def run(game_dir,out,depots,profile=None,*,client_factory=MaterialClient,survey_factory=Client,
        snapshot_reader=read_fresh,sleeper=time.sleep):
    depots=_depots(depots);out=Path(out);root=Path(game_dir)/'config/twob2tkit/automation'
    if out.exists() and any(out.iterdir()):raise StockBlocked('Original stock-audit directory exists; no replay or overwrite')
    initial=snapshot_reader(root);require_unlocked(root,initial)
    task=initial.get('material_task')or{}
    if (not initial.get('player_uuid') or initial.get('screen') or task.get('occupied') or task.get('process_alive')
            or any(initial.get(k)for k in ('navigating','native_material_busy','chopping','borer_active','printing',
                                          'planter_active','feeder_active','fisher_active'))
            or initial.get('build_job',{}).get('active') or initial.get('professional_printer',{}).get('enabled')
            or initial.get('supervision_lease',{}).get('kind')not in (None,'parking')
            or initial.get('flight')is not True):
        raise StockBlocked('Storage audit awaits a healthy idle guarded high park and sole controller')
    _check(initial,initial)
    context={'server':initial['server'],'dimension':initial['dimension']}
    path=Path(profile)if isinstance(profile,(str,Path))else profile_path(root,context)
    settings=(deepcopy(profile)if isinstance(profile,dict)else json.loads(path.read_text())if path.exists()else{})
    if settings and (server_key(settings.get('server'))!=server_key(initial['server'])
                     or settings.get('dimension')!=initial['dimension']):raise StockBlocked('Registered house profile belongs to another server/dimension')
    _ground_reach_profile(settings)  # Validate explicit opt-in before any lease or game request.
    out.mkdir(parents=True);(out/'receipts').mkdir();report={'schema':1,'phase':'preflight','complete':False,'read_only_inventory':True,
        'evidence_scope':'two_distinct_stable_current_menu_frames_per_container_not_atomic_all_depots',
        'depots':depots,'scope':_identity(initial),'inventory_before':_inventory(initial),'containers':[],
        'loose_counts':{},'packed_counts':{},'pending':None}
    write_json(out/'scope.json',{'depots':depots,'scope':report['scope']})
    write_json(out/'stock-audit.json',report);client=session=None;finish_started=False
    try:
        survey=survey_factory(root,out/'preflight',server=initial['server'])
        pos=initial['pos'];low=[math.floor(pos[0]-.35),-64,math.floor(pos[2]-.35)];high=[math.floor(pos[0]+.35),319,math.floor(pos[2]+.35)]
        column=_scan(survey,low,high);write_json(out/'current-park-column.json',column)
        ground=max((r['pos'][1]+1 for r in column['blocks']if r.get('fluid')or not r.get('passable',False)),default=None)
        fresh=_check(survey.status(),initial)
        if ground is None or fresh['pos'][1]-ground<20 or math.dist(pos,fresh['pos'])>.05:
            raise StockBlocked('Current loaded column lacks twenty-block parking clearance')
        client=client_factory(root,out,server=initial['server'],remote_finish='guard',park_target=list(fresh['pos']),record_experience=False)
        progress=getattr(client,'start_progress',None)
        if callable(progress):progress('仓库只读核验',len(depots),phase='实际箱子与稳定库存')
        report.update(task_session=client.task,lease_id=client.heartbeat.id)
        write_json(out/'owner.json',{'task_session':client.task,'lease_id':client.heartbeat.id,'scope':report['scope']})
        session=_Session(client,initial,report,out);seen=set()
        for index,pos in enumerate(depots):
            _exit_storage(session,settings)
            report['stage']={'op':'storage_approach','pos':pos};session.save()
            _travel_to(session,pos,session.status,[])
            key,state,positions=_container(session,pos)
            if key in seen:
                progress=getattr(client,'set_progress',None)
                if callable(progress):progress(done=index+1,phase='已核对同一库存的重复位置')
                continue
            report['stage']={'op':'container_open','pos':pos};session.save()
            opened=_open_container(session,pos,state,settings)
            opened_id=(opened.get('menu')or{}).get('id')
            if type(opened_id)is not int:raise StockBlocked('The source container menu acknowledgement is unavailable')
            body_clearance=_body_clearance(session)
            kind,slots=MENU_LAYOUTS[_state_parts(state)[0]]
            if _state_parts(state)[0]=='minecraft:chest' and len(positions)==2:slots=54
            frame=_read_menu(session,slots,sleeper,opened_id,kind)
            after_key,after_state,after_positions=_container(session,pos)
            if (after_key!=key or not _same_opened_state(state,after_state) or after_positions!=positions):
                raise StockBlocked('Actual container changed after opening')
            rows=deepcopy(frame['menu']['slots'][:-36]);loose,packed,unknown=_contents(rows)
            record={'identity':key,'positions':positions,'block_state':state,'opened_block_state':after_state,'observed_at':frame['time'],
                    'menu_id':frame['menu']['id'],'menu_type':kind,'slots':rows,'loose_counts':loose,'packed_counts':packed,
                    'unknown_packed_slots':unknown,'two_distinct_menu_frames':True,'reached_body_clearance':body_clearance}
            if kind=='BlastFurnaceMenu':
                record['visible_slot_roles']={'0':'input','1':'fuel','2':'output'}
            report['containers'].append(record);seen.add(key)
            session.checked('close_menu');session.save()
            progress=getattr(client,'set_progress',None)
            if callable(progress):progress(done=index+1,phase='真实容器库存已核对')
        _exit_storage(session,settings)
        report['stage']={'op':'guarded_finish'};session.save()
        current=session.status();point=current['pos']
        column=_scan(session,[math.floor(point[0]-.35),-64,math.floor(point[2]-.35)],
                     [math.floor(point[0]+.35),319,math.floor(point[2]+.35)])
        ground=max((r['pos'][1]+1 for r in column['blocks']if r.get('fluid')or not r.get('passable',False)),default=None)
        if ground is None or ground+24>315:raise StockBlocked('Actual final column lacks a bounded guarded park')
        client.park_target=[point[0],max(point[1],ground+24),point[2]]
        report['pending']={'op':'guarded_finish','request_before':client.last};session.save()
        finish_started=True;client.finish();report['pending']=None
        proof=_finish_proof(client,initial);write_json(out/'finish-proof.json',proof)
        loose,packed=Counter(),Counter()
        for row in report['containers']:loose.update(row['loose_counts']);packed.update(row['packed_counts'])
        report.update(phase='done',complete=True,loose_counts=dict(loose),packed_counts=dict(packed),
                      packed_metadata_complete=all(not row['unknown_packed_slots']for row in report['containers']),
                      inventory_after=_inventory(proof['current_parking']),finished_at=proof['current_parking']['time'])
    except Exception as error:
        report.update(phase='waiting',complete=False,error=type(error).__name__+': '+str(error))
        if client is not None and not report.get('pending') and client.native_inflight:
            report['pending']={'op':(report.get('stage')or{}).get('op'),'request_id':client.last,
                               'native_inflight':deepcopy(client.native_inflight),'world_session':client.world}
        if client is not None and report.get('pending'):
            report['pending'].update(request_id=client.last,native_inflight=deepcopy(client.native_inflight))
            report['cleanup_deferred']='Original operation retained; no finish or request replay'
        elif client is not None and not finish_started:
            try:
                _exit_storage(session,settings)
                current=session.status();point=current['pos']
                column=_scan(session,[math.floor(point[0]-.35),-64,math.floor(point[2]-.35)],
                             [math.floor(point[0]+.35),319,math.floor(point[2]+.35)])
                ground=max((r['pos'][1]+1 for r in column['blocks']if r.get('fluid')or not r.get('passable',False)),default=None)
                if ground is None or ground+24>315:raise StockBlocked('Actual cleanup column lacks a bounded guarded park')
                client.park_target=[point[0],max(point[1],ground+24),point[2]]
                client.finish();report['finish_proof']=_finish_proof(client,initial)
            except Exception as cleanup:report['cleanup_error']=type(cleanup).__name__+': '+str(cleanup)
    write_json(out/'stock-audit.json',report)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,default=DEFAULT_GAME)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--depot',type=int,nargs=3,action='append',required=True)
    parser.add_argument('--profile',type=Path)
    args=parser.parse_args(argv)
    try:
        report=run(args.game_dir,args.out,args.depot,args.profile)
        print(json.dumps({k:report.get(k)for k in ('phase','complete','loose_counts','packed_counts','packed_metadata_complete','error')},ensure_ascii=False))
        return 0 if report['complete'] else 2
    except (RuntimeError,ValueError,OSError)as error:
        print(json.dumps({'phase':'waiting','complete':False,'error':str(error)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
