"""Reuse Kit farm/feeding/storage primitives and native fisher controls under one idle owner."""
from copy import deepcopy
from contextlib import contextmanager
import fcntl
import json
import math
from pathlib import Path
import time

from farm_caretaker import validate_profile as validate_caretaker
from farm_caretaker_stages import create_stages
from idle_service import IdleYield,read
from kit_runtime.journal import write_json
from material_jobs.protocol import server_key,validate_request
from material_jobs_backend import JobClient,create_backend,owns_material_state
from material_jobs.acquisition import _travel, _terminal_guard_route
from material_jobs.navigation import settled_state
from potato_farm import run as plant,plan as planting_plan,valid_entity_scope
from potato_farm import _key,_properties
from potato_loot_flight import make_pickup


def free_slots(state):
    rows=state.get('inventory')
    if not isinstance(rows,list):return 0
    carried=[r for r in rows if type(r.get('slot'))is int and 0<=r['slot']<36]
    if len(carried)!=36 or len({r['slot'] for r in carried})!=36:return 0
    return sum(r.get('count')==0 and r.get('item')=='minecraft:air' for r in carried)


def _box_hit(start,end,low,high,padding=.35):
    first,last=0.0,1.0
    for a,b,lo,hi in zip(start,end,low,high):
        delta=b-a;lo-=padding;hi+=padding
        if abs(delta)<1e-9:
            if not lo<=a<=hi:return False
            continue
        near,far=sorted(((lo-a)/delta,(hi-a)/delta));first=max(first,near);last=min(last,far)
        if first>last:return False
    return True


def verify_shore(state,scan,shore,*,require_standing=True,ground_proof=None):
    if (require_standing and (math.dist(state.get('pos',[0,0,0]),shore['stand'])>.15
                or state.get('on_ground') is not True and not (isinstance(ground_proof,dict)
                    and ground_proof.get('scope')=='owned_completed_ground_walk_read_only_settlement'
                    and ground_proof.get('world_session')==state.get('world_session')
                    and ground_proof.get('observed_span_ms',0)>=400
                    and math.dist(state.get('pos',[0,0,0]),ground_proof.get('settled',[1e9,1e9,1e9]))<=.08))
            or state.get('under_water') is not False or not valid_entity_scope(scan.get('scan_entity_scope'))
            or not isinstance(scan.get('scan_entities'),list) or scan.get('unloaded_chunks',0) or not isinstance(scan.get('blocks'),list)):
        raise RuntimeError('Fishing requires the actual registered dry shore and a fresh bounded empty entity scan')
    by={};foot=[math.floor(v) for v in shore['stand']];floor=(foot[0],foot[1]-1,foot[2])
    actual_range=state.get('fisher_chest_range')
    if type(actual_range)is not int or not 2<=actual_range<=24:raise RuntimeError('Actual native fishing chest range is unavailable or exceeds the bounded scan')
    radius=max(8,actual_range)
    for row in scan['blocks']:
        p=row.get('pos')
        if (not isinstance(p,list) or len(p)!=3 or any(type(v)is not int for v in p)
                or tuple(p) in by or type(row.get('fluid'))is not bool or type(row.get('block_entity'))is not bool
                or not foot[0]-radius<=p[0]<=foot[0]+radius or not foot[1]-8<=p[1]<=foot[1]+8 or not foot[2]-radius<=p[2]<=foot[2]+radius):
            raise RuntimeError('Fishing scan metadata is incomplete')
        by[tuple(p)]=row
        if row['block_entity']:raise RuntimeError('Fishing cannot use a shore with nearby containers; native arbitrary auto-deposit is excluded')
        if 'minecraft:lava' in row.get('state',''):raise RuntimeError('Fishing shore contains lava')
    support=by.get(floor,{})
    if support.get('solid') is not True or support.get('fluid') is not False:raise RuntimeError('Fishing lacks observed dry solid support')
    if tuple(foot) in by or (foot[0],foot[1]+1,foot[2]) in by:raise RuntimeError('Fishing body/headroom is occupied')
    water=by.get(tuple(shore['water']),{})
    if water.get('state')!='Block{minecraft:water}[level=0]' or water.get('fluid') is not True:raise RuntimeError('Configured fishing water is not an observed source')
    eye=[shore['stand'][0],shore['stand'][1]+1.62,shore['stand'][2]]
    aim=[shore['water'][i]+(.8 if i==1 else .5) for i in range(3)]
    body_low=[shore['stand'][0]-.31,shore['stand'][1],shore['stand'][2]-.31]
    body_high=[shore['stand'][0]+.31,shore['stand'][1]+1.8,shore['stand'][2]+.31]
    for entity in scan['scan_entities']:
        bounds=entity.get('bounds') or {};low,high=bounds.get('min'),bounds.get('max')
        if (type(entity.get('hostile'))is not bool or type(entity.get('alive'))is not bool
                or not isinstance(low,list) or not isinstance(high,list) or len(low)!=3 or len(high)!=3
                or any(type(v)not in(int,float) or not math.isfinite(v) for v in low+high)
                or any(a>b for a,b in zip(low,high))):raise RuntimeError('Actual fishing entity bounds/hostility are unavailable')
        if entity['alive'] is not True:continue
        distance=math.sqrt(sum(max(lo-v,0,v-hi)**2 for v,lo,hi in zip(shore['stand'],low,high)))
        if entity['hostile'] and distance<=8:raise RuntimeError('A hostile is inside the fishing shore danger radius')
        body=all(a<d and b>c for a,b,c,d in zip(body_low,body_high,low,high))
        if body or _box_hit(eye,aim,low,high):raise RuntimeError('A real entity intersects the fishing body or casting corridor')
    delta=[shore['water'][i]+(.8 if i==1 else .5)-eye[i] for i in range(3)]
    expected_yaw=math.degrees(math.atan2(-delta[0],delta[2]));expected_pitch=math.degrees(math.atan2(-delta[1],math.hypot(delta[0],delta[2])))
    if abs((shore['yaw']-expected_yaw+180)%360-180)>8 or abs(shore['pitch']-expected_pitch)>8:
        raise RuntimeError('Registered fishing view does not face the verified near water')


class _MovementClient:
    """Existing travel planner, with durable per-native-movement intents rather than new navigation."""
    def __init__(self,runner):self.runner=runner
    def __getattr__(self,name):return getattr(self.runner.client,name)
    def request(self,op,**params):
        if op in ('navigate','walk'):return self.runner._send_movement(op,**params)
        return self.runner.client.request(op,**params)


class IdleJobClient(JobClient):
    def __init__(self,runner,*args,**kwargs):
        self.idle_service_id=runner.service.key;self.idle_runner=runner;runner.client=self
        super().__init__(*args,**kwargs)
    def raw(self,*args,**kwargs):
        previous=self.owner.checking;self.owner.checking=True
        try:state=super().raw(*args,**kwargs)
        finally:self.owner.checking=previous
        pending=self.idle_runner.ledger.get('pending');inflight=getattr(self,'native_inflight',None)
        opening=self.idle_runner.ledger.get('opening_pending')
        if (isinstance(opening,dict) and isinstance(inflight,dict) and inflight.get('op')=='material_session'
                and opening.get('request_envelope')!=inflight):
            opening['request_envelope']=deepcopy(inflight);write_json(self.idle_runner.ledger_path,self.idle_runner.ledger)
        cleanup=self.idle_runner.ledger.get('cleanup_pending')
        if (isinstance(cleanup,dict) and isinstance(inflight,dict) and inflight.get('op')==cleanup.get('op')
                and cleanup.get('request_envelope')!=inflight):
            cleanup['request_envelope']=deepcopy(inflight);write_json(self.idle_runner.ledger_path,self.idle_runner.ledger)
        if (isinstance(pending,dict) and pending.get('op') in ('navigate','walk') and isinstance(inflight,dict)
                and inflight.get('op')==pending['op'] and inflight.get('task_session')==getattr(self,'task',None)
                and pending.get('request_envelope')!=inflight):
            pending['request_envelope']=deepcopy(inflight);write_json(self.idle_runner.ledger_path,self.idle_runner.ledger)
        if not self.idle_runner.cleaning:
            try:self.idle_runner.service.checkpoint(state)
            except IdleYield as yielded:
                # Cancel before Client.request's finally clears the exact in-flight envelope.
                self.idle_runner.stop(str(yielded),normal=False)
                raise
        return state
    def request(self,op,**params):
        if op in ('navigate','walk') and not self.idle_runner.dispatching_movement:
            return self.idle_runner._send_movement(op,**params)
        if op!='material_session':return super().request(op,idle_service_id=self.idle_service_id,**params)
        ledger=self.idle_runner.ledger
        if ledger.get('opening_pending'):raise RuntimeError('Original session admission cannot be replayed')
        ledger['opening_pending']={'op':op,'params':deepcopy(params),'world_session':self.world,
            'revision':self.rev,'task_session':self.task,'lease_id':self.heartbeat.id,'stage':'intent_before_dispatch'}
        write_json(self.idle_runner.ledger_path,ledger)
        try:
            reply=super().request(op,idle_service_id=self.idle_service_id,**params)
            ledger['opening_pending']['receipt']={k:reply.get(k)for k in ('id','phase','time','detail')}
            write_json(self.idle_runner.ledger_path,ledger);lease=reply.get('supervision_lease')or{}
            if (reply.get('phase')!='done' or reply.get('world_session')!=self.world or reply.get('id')!=self.last
                    or lease.get('kind')!='materials' or lease.get('job_session')!=self.task or lease.get('id')!=self.heartbeat.id):
                raise RuntimeError('Session admission is unconfirmed; preserve the original request')
            ledger['receipts'].append(ledger['opening_pending']|{'outcome':'material_session_admitted_not_world_goal'})
            ledger['opening_pending']=None;write_json(self.idle_runner.ledger_path,ledger);return reply
        except BaseException as error:
            # Base MaterialClient closes its heartbeat when a constructor fails.
            # Remain inside this request until the exact admission/release is
            # proved, so that outer close cannot create an orphaned native lease.
            self.idle_runner.wait_opening_release(str(error));raise


class NativeRunner:
    def __init__(self,service,job,directory):
        self.service,self.job,self.out=service,job,Path(directory)
        self.client=self.backend=None;self.cleaning=False;self.lock=None;self.started=service.clock()
        self.ledger_path=self.out/'runner.json';self.ledger={'schema':1,'job':job,'pending':None,'cleanup_pending':None,'opening_pending':None,'receipts':[]}
        self.farm=None;self.stop_result=None
        self.ground_proof=None
        self.approach_shore=None
        self.dispatching_movement=False
        self.unresolved_paths=[]
        self.field_context=None
        self.opening_state=None
    def identity(self):
        c=self.client
        return {'task_session':getattr(c,'task',None),'lease_id':getattr(getattr(c,'heartbeat',None),'id',None)}
    def owns(self,state):
        return self.client is not None and hasattr(self.client,'task') and self.client.heartbeat is not None and owns_material_state(self.client,state)
    def _registered_farm(self):
        path=self.service.profile.get('caretaker_profile')
        if not path:raise RuntimeError('WAIT_REGISTERED_FARM: no explicit farm/livestock/storage profile')
        profile=validate_caretaker(read(path))
        if profile['server']!=self.service.profile['server'] or profile['dimension']!=self.service.profile['dimension']:raise RuntimeError('Farm profile belongs to another scope')
        import hashlib
        key=hashlib.sha256((profile['server']+'|'+profile['dimension']).encode()).hexdigest()[:20]
        home=self.service.root/'farm-caretakers'/key;registry=read(home/'registry.json')
        if registry.get('profile')!=profile:raise RuntimeError('Farm profile is not the existing explicit registration')
        journal=Path(registry['directory'])/'caretaker.json'
        if journal.exists() and read(journal).get('pending'):raise RuntimeError('WAIT_RECONCILE: original caretaker action is unresolved')
        lock_path=home/'worker.lock'
        if not lock_path.exists():raise RuntimeError('Existing caretaker worker lock is unavailable')
        self.lock=lock_path.open('rb')
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as error:self.lock.close();self.lock=None;raise RuntimeError('CARETAKER_BUSY: another caretaker owns the farm') from error
        self.farm=profile
        return profile
    def _open(self,state,profile):
        self.opening_state=deepcopy(state)
        request=validate_request({'schema':1,'id':'idle-'+self.service.key+'-'+str(self.service.book['sequence']),
            'mode':'item','targets':{'minecraft:baked_potato':profile['cooked_food_reserve']},'created_at':max(1,state['time']),
            'context':{k:state[k] for k in ('server','dimension','world_session')}|
                      {'expected_revision':state['control_revision'],'start_pos':state['pos']}})
        backend_out=self.out/'backend';backend_out.mkdir(parents=True,exist_ok=True)
        self.backend=create_backend(request,self.service.root,backend_out,self.service.checkpoint)
        if any(p not in self.backend.profile.get('depots',[]) for p in profile['depots']):raise RuntimeError('Caretaker uses an unapproved material depot')
        self.backend.profile['park_target']=profile['park_target'][:];self.backend.sequence+=1
        control=self.backend.out/('control-%03d'%self.backend.sequence)
        initial_park=profile['park_target'][:];parking=state.get('supervision_lease')or{}
        if (parking.get('kind')=='parking' and parking.get('world_session')==state['world_session']
                and isinstance(parking.get('park_target'),list) and len(parking['park_target'])==3
                and math.dist(state['pos'],parking['park_target'])<=2):initial_park=parking['park_target'][:]
        client=IdleJobClient(self,self.backend,self.service.root,control,server=state['server'],
            record_experience=True,experience_state=self.backend.experience_state(),remote_finish='guard',park_target=initial_park)
        client.park_target=profile['park_target'][:]  # Ordinary successful finish uses the registered park.
        self.backend.client=client
    def _send(self,op,cleanup=False,**params):
        key='cleanup_pending' if cleanup else 'pending'
        if self.ledger.get(key):raise RuntimeError('Unknown native idle request must not be replayed')
        self.ledger[key]={'op':op,'params':deepcopy(params),'world_session':self.client.world,'revision':self.client.rev}
        write_json(self.ledger_path,self.ledger)
        reply=self.client.request(op,**params)
        self.ledger[key]['receipt']={k:reply.get(k) for k in ('id','phase','time','detail')};write_json(self.ledger_path,self.ledger)
        if reply.get('phase')!='done':raise RuntimeError('Idle request did not produce a confirmed native result')
        self.ledger['receipts'].append(self.ledger[key]);self.ledger[key]=None;write_json(self.ledger_path,self.ledger)
        return reply
    def _send_movement(self,op,*,require_exact_pose=False,require_ground_landing=False,**params):
        if op not in ('navigate','walk') or self.ledger.get('pending'):raise RuntimeError('Unknown original movement cannot be replayed')
        from potato_harvest import _counts
        before=self.client.status();self.service.checkpoint(before)
        self.ledger['pending']={'op':op,'params':deepcopy(params),'world_session':self.client.world,
            'revision':self.client.rev,'position_before':before['pos'][:],'before_counts':dict(_counts(before))}
        write_json(self.ledger_path,self.ledger)
        self.dispatching_movement=True
        try:reply=self.client.request(op,**params)
        finally:self.dispatching_movement=False
        self.ledger['pending']['receipt']={k:reply.get(k) for k in ('id','phase','time','detail')};write_json(self.ledger_path,self.ledger)
        if reply.get('phase')!='done':
            after=self.client.status()
            # The existing travel planner may replan only a positively stopped
            # exact waiting request. This preserves its result as failed, never completed.
            if _terminal_guard_route(self.client,reply,after) and _counts(after)==_counts(before):
                self.ledger['pending'].update(outcome='native_terminal_not_arrived',goal_completed=False)
                self.ledger['receipts'].append(self.ledger['pending']);self.ledger['pending']=None;write_json(self.ledger_path,self.ledger)
                return reply
            raise RuntimeError('Movement outcome is unknown; preserve its original intent without replay')
        if op=='walk':
            if require_ground_landing:
                if params.get('restore_flight') is not False:raise RuntimeError('Fishing landing must use the owned ground-walk proof')
                landed=self.client._settle_owned_ground_walk(self.client.status())
                proof_path=Path(self.client.out)/'park-ground-settlement.json';proof=read(proof_path)
                if (proof.get('scope')!='owned_completed_ground_walk_read_only_settlement'
                        or proof.get('world_session')!=self.client.world or proof.get('observed_span_ms',0)<400
                        or proof.get('request_id')!=getattr(self.client,'last',None)
                        or landed.get('on_ground') is not True or landed.get('flight') is not False
                        or math.dist(landed['pos'],params['target'])>.15):
                    raise RuntimeError('Controlled fishing landing was not actually proved')
                self.ground_proof=deepcopy(proof);after=landed
            else:
                after=self.client.status()
                if math.hypot(after['pos'][0]-params['target'][0],after['pos'][2]-params['target'][2])>params.get('arrival',.65) or abs(after['pos'][1]-params['target'][1])>1.2:
                    raise RuntimeError('Completed ordinary walk does not match its native arrival bounds')
        else:
            navigation=reply.get('material_air_navigation') or {}
            if (reply.get('id')!=getattr(self.client,'last',None) or reply.get('world_session')!=self.client.world
                    or navigation.get('phase')!='confirmed' or navigation.get('outcome')!='done'
                    or navigation.get('world_session')!=self.client.world
                    or type(navigation.get('stable_ticks'))is not int or navigation['stable_ticks']<8
                    or type(navigation.get('restored_ticks'))is not int or navigation['restored_ticks']<8
                    or navigation.get('injury_interrupted') is not False):
                raise RuntimeError('Movement lacks the existing native precise-arrival/restore proof')
            if require_exact_pose:
                # Native arrival proves real stillness while allowing Minecraft's
                # gravity term. Then verify two actual shore frames; no fabricated
                # on_ground flag is substituted for the completed landing proof.
                after=self._confirm_shore_pose(self.approach_shore,during_movement=True)
            else:
                after=self.client.status()
                if math.dist(after['pos'],params['target'])>max(.55,params.get('arrival',.25)):
                    raise RuntimeError('Native arrival reply does not match the actual target position')
            if after.get('flight') is not True:raise RuntimeError('Flight restoration was not observed after the owned navigation')
        if _counts(after)!=_counts(before):raise RuntimeError('Inventory changed during movement; keep the original movement record for review')
        self.ledger['pending'].update(outcome='observed_arrival',position_proof={k:after.get(k) for k in ('time','pos','on_ground','flight','velocity')},
            ground_proof=deepcopy(self.ground_proof) if op=='walk' else None)
        self.ledger['receipts'].append(self.ledger['pending']);self.ledger['pending']=None;write_json(self.ledger_path,self.ledger)
        return reply
    def _shore_scan(self,shore,*,during_movement=False):
        feet=[math.floor(v) for v in shore['stand']]
        radius=self.client.status().get('fisher_chest_range')
        if type(radius)is not int or not 2<=radius<=24:raise RuntimeError('Actual native fishing chest range is unavailable')
        radius=max(8,radius)
        params={'min':[feet[0]-radius,feet[1]-8,feet[2]-radius],'max':[feet[0]+radius,feet[1]+8,feet[2]+radius],'details':True}
        if during_movement:return self.client.request('scan',**params)
        return self._send('scan',**params)
    def _approach_shore(self,shore):
        self.approach_shore=deepcopy(shore)
        state=self.client.status();verify_shore(state,self._shore_scan(shore),shore,require_standing=False)
        if math.dist(state['pos'],shore['stand'])>.15 or state.get('on_ground') is not True:
            trace=[];hover=[shore['stand'][0],shore['stand'][1]+.4,shore['stand'][2]]
            _travel(_MovementClient(self),hover,self.service.checkpoint,trace)
            write_json(self.out/'shore-travel-trace.json',{'world_session':self.client.world,'target':hover,'trace':trace})
            verify_shore(self.client.status(),self._shore_scan(shore),shore,require_standing=False)
            self._send_movement('walk',target=shore['stand'][:],arrival=.15,restore_flight=False,seconds=10,require_ground_landing=True)
            grounded=self.client.status()
            self._send_movement('navigate',target=grounded['pos'][:],arrival=.15,air_only=True,seconds=8,require_exact_pose=True)
        return self._confirm_shore_pose(shore)
    def _confirm_shore_pose(self,shore,*,during_movement=False):
        previous=None
        for _ in range(12):
            self.service.checkpoint();observed=self._shore_scan(shore,during_movement=during_movement)
            verify_shore(observed,observed,shore,ground_proof=self.ground_proof)
            velocity=observed.get('velocity');keys=observed.get('movement_keys') or {}
            if (observed.get('flight') is not True or observed.get('guard_armed') is not True or observed.get('guard_pve_only') is not True
                    or not isinstance(velocity,list) or len(velocity)!=3 or any(type(v)not in(int,float) or not math.isfinite(v) for v in velocity)
                    or math.hypot(velocity[0],velocity[2])>.03 or abs(velocity[1])>.1
                    or not {'forward','back','jump','sneak'}.issubset(keys) or any(v is not False for v in keys.values())):
                raise RuntimeError('Restored Flight fishing pose or empty native input was not actually confirmed')
            if (previous is not None and type(observed.get('time'))is int and observed['time']-previous['time']>=400
                    and math.dist(observed['pos'],previous['pos'])<=.08):
                write_json(self.out/'shore-arrival.json',{'scope':'owned_ground_landing_then_same_pose_flight_and_two_bounded_scans',
                    'world_session':self.client.world,'ground_proof':self.ground_proof,'observed_times':[previous['time'],observed['time']],
                    'position':observed['pos'],'flight':True,'on_ground_observed':observed.get('on_ground'),'server_verified':False})
                return observed
            if previous is None:previous=observed
            time.sleep(.05)
        raise RuntimeError('Fishing arrival did not produce two distinct stable actual observations')
    def _registered_plant_job(self,state,profile):
        from farm_preparation import PreparationWait,preparation_lock,assert_preparation_resolved
        from potato_harvest import _counts,run as harvest
        registry_path=Path(self.service.profile['plant_registries'][(self.service.book['sequence']-1)%len(self.service.profile['plant_registries'])])
        allowed=(self.service.root/'farms').resolve()
        if registry_path.name!='registry.json' or not registry_path.resolve().is_relative_to(allowed):raise RuntimeError('Planting must reference an existing local farm registry')
        registry=read(registry_path);scope=registry.get('scope') or {};layout=scope.get('layout') or {}
        if scope.get('server')!=profile['server'] or scope.get('dimension')!=profile['dimension'] or registry.get('world_session')!=state['world_session']:raise RuntimeError('Registered planting scope/world changed')
        request={'authorized':True,'center':layout.get('center'),'radius':layout.get('radius',2),'crop':layout.get('crop','potato')}
        if planting_plan(request)!=layout:raise RuntimeError('Registered planting layout is malformed')
        try:
            with self._field_session(preparation_lock(self.service.root,state,request)):
                assert_preparation_resolved(self.service.root,state,request)
                if request['crop']=='wheat':
                    active=registry_path.parent/'harvest-active.json'
                    if active.exists():
                        prior=Path(read(active)['journal']);saved=read(prior)
                        if saved.get('pending') or saved.get('cleanup_pending'):
                            self.unresolved_paths.append(prior);self.ledger['blocked_journal']=str(prior);write_json(self.ledger_path,self.ledger)
                            return {'phase':'waiting','code':'WAIT_RECONCILE','pending':True,'journal':str(prior),'active_journal':str(prior)}
                    planted_path=Path(registry['directory'])/('wheat-farm-'+registry_path.parent.name+'.json')
                    planted=read(planted_path)
                    if planted.get('scope')!=scope or planted.get('world_session')!=self.client.world or planted.get('pending') or planted.get('cleanup_pending'):
                        self.unresolved_paths.append(planted_path)
                        return {'phase':'waiting','code':'WAIT_RECONCILE','pending':True,'journal':str(planted_path)}
                    scan=self._send('scan',min=layout['scan_min'],max=layout['scan_max'],details=True)
                    if not valid_entity_scope(scan.get('scan_entity_scope')) or not isinstance(scan.get('blocks'),list) or scan.get('unloaded_chunks',0):raise RuntimeError('Registered wheat crop scan is incomplete')
                    rows={tuple(row['pos']):row for row in scan['blocks']}
                    if any(_properties(rows.get(tuple(pos),{}),'farmland','moisture',7) is None for pos in layout['cells']):
                        return {'phase':'waiting','code':'WAIT_EXISTING_FARMLAND','pending':False}
                    mature=[pos for pos in layout['cells'] if planted.get('cells',{}).get(_key(pos),{}).get('planted') is True
                        and _properties(rows.get((pos[0],pos[1]+1,pos[2]),{}),'wheat','age',7)==7][:4]
                    if mature:
                        if _counts(scan)['minecraft:wheat_seeds']<5:return {'phase':'waiting','code':'WAIT_ACTUAL_WHEAT_SEED_RESERVE','pending':False}
                        center=layout['center'];target=[center[0]+.5,center[1]+1.6,center[2]+.5];trace=[]
                        _travel(_MovementClient(self),target,self.service.checkpoint,trace)
                        result=harvest(self.client,{**request,'cells':mature,'bonemeal':False},self.out/'registered-wheat-harvest',
                            self.service.checkpoint,max_cells=4,bonemeal_budget=0,
                            pickup=make_pickup(center,radius=layout['radius'],checkpoint=self.service.checkpoint,crop='wheat'))
                        self.ledger['harvest_result']=deepcopy(result);write_json(self.ledger_path,self.ledger)
                        journal=Path(result.get('active_journal') or result['journal']);inner=read(journal)
                        if inner.get('pending') or inner.get('cleanup_pending'):self.unresolved_paths.append(journal)
                        return result|{'pending':self.has_unknown()}
                return plant(self.client,request,Path(registry['directory']),self.service.checkpoint,
                             max_cells=4,existing_farmland_only=True)|{'pending':self.has_unknown()}
        except PreparationWait as waiting:
            return {'phase':'waiting','code':waiting.code,'detail':str(waiting),'pending':False}
    @contextmanager
    def _field_session(self,context):
        context.__enter__();self.field_context=context
        # The field remains locked through the caller's native cleanup/park,
        # not merely through registry checks or the harvest function return.
        yield
    def run(self,state):
        if self.job=='fish' and not self.service.profile['fishing']['enabled']:
            return {'phase':'idle','code':'FISHING_NOT_CONFIGURED','pending':False}
        if self.job=='plant' and not self.service.profile['plant_registries']:
            return {'phase':'idle','code':'PLANTING_NOT_REGISTERED','pending':False}
        try:profile=self._registered_farm()
        except RuntimeError as error:
            if str(error).startswith(('WAIT_','CARETAKER_BUSY')):
                return {'phase':'waiting','code':str(error).split(':',1)[0],'detail':str(error),'pending':False}
            raise
        if self.job=='breed' and not profile.get('livestock_types'):return {'phase':'idle','code':'LIVESTOCK_NOT_REGISTERED','pending':False}
        if self.job=='breed':
            if any(kind not in ('minecraft:cow','minecraft:sheep') for kind in profile['livestock_types']):
                return {'phase':'waiting','code':'WAIT_SUPPORTED_LIVESTOCK','pending':False}
            from potato_harvest import _counts
            if _counts(state)['minecraft:wheat']<2:
                return {'phase':'waiting','code':'WAIT_ACTUAL_FEED_FOOD','detail':'Carry two actual wheat before an idle feeding attempt; no speculative supply action','pending':False}
        if self.job=='harvest_store' and not profile.get('potato_fields'):return {'phase':'idle','code':'FIELD_NOT_REGISTERED','pending':False}
        if self.job=='fish':
            shore=self.service.profile['fishing']['shore']
            if state.get('idle_fishing_protocol')!=1 or state.get('fisher_deposit_allowed') is not False:
                return {'phase':'waiting','code':'WAIT_NO_DEPOSIT_FISHING_CAPABILITY','pending':False}
            if math.hypot(state['pos'][0]-shore['stand'][0],state['pos'][2]-shore['stand'][2])>384:
                return {'phase':'waiting','code':'WAIT_BOUNDED_SHORE_ROUTE','pending':False}
            if free_slots(state)<self.service.profile['fishing']['minimum_free_slots']:return {'phase':'idle','code':'WAIT_FISHING_SPACE','pending':False}
            rod=next((r for r in state['inventory'] if r.get('slot',36)<36 and r.get('item')=='minecraft:fishing_rod'
                and r.get('count')==1 and type(r.get('durability'))is int and r['durability']>32),None)
            if rod is None:return {'phase':'idle','code':'WAIT_ACTUAL_ROD','pending':False}
        self._open(state,profile)
        if self.job in ('harvest_store','breed','cook_store'):
            from material_plan import inventory_counts
            cycle={'id':self.service.book['sequence'],'directory':str(self.out),'world_session':state['world_session'],
                   'baseline':dict(inventory_counts(state)),'receipts':{}}
            stages=create_stages(self.client,self.backend)
            return stages[self.job](profile,cycle,self.out/self.job,self.service.checkpoint)
        if self.job=='plant':
            return self._registered_plant_job(state,profile)
        shore=self.service.profile['fishing']['shore'];self._approach_shore(shore)
        self._send('select_item',item='minecraft:fishing_rod',slot=rod['slot'])
        if self.client.status().get('hand',{}).get('item')!='minecraft:fishing_rod':raise RuntimeError('Selected fishing rod was not observed')
        self._send('look',yaw=shore['yaw'],pitch=shore['pitch'])
        aimed=self.client.status()
        if abs((aimed.get('yaw',0)-shore['yaw']+180)%360-180)>1.5 or abs(aimed.get('pitch',0)-shore['pitch'])>1.5:raise RuntimeError('Fishing view was not observed')
        reply=self._send('fisher_start')
        started=self.client.status()
        if (reply.get('fisher_active') is not True or started.get('fisher_active') is not True
                or reply.get('fisher_deposit_allowed') is not False or started.get('fisher_deposit_allowed') is not False):
            raise RuntimeError('Native scoped fisher did not confirm active with automatic deposit disabled')
        self.started=self.service.clock();return {'phase':'active','pending':False,'native_receipt':{k:reply.get(k) for k in ('id','phase','time')}}
    def should_finish(self,state):
        return (self.service.clock()-self.started>=self.service.profile['fishing']['duration_seconds']
                or free_slots(state)<4 or state.get('fisher_active') is not True or state.get('fisher_deposit_allowed') is not False)
    def has_unknown(self):
        if self.ledger.get('pending') or self.ledger.get('cleanup_pending') or self.ledger.get('opening_pending'):return True
        paths=list(self.out.rglob('*.json'))
        paths.extend(self.unresolved_paths)
        if self.job=='plant':
            for registry in self.service.profile['plant_registries']:
                value=read(registry);paths.extend(Path(value['directory']).glob('*-farm-*.json'))
        for path in paths:
            if path.stat().st_size<=2_000_000:
                try:
                    value=json.loads(path.read_text())
                    if isinstance(value,dict) and value.get('pending'):return True
                except ValueError:return True
        return False
    def wait_opening_release(self,reason):
        c=self.client;previous=None
        while self.ledger.get('opening_pending') or self.ledger.get('cleanup_pending'):
            state=self.service.observer()
            stamp=state.get('time')
            if type(stamp)is int and -1000<=int(time.time()*1000)-stamp<=2500:c.heartbeat.touch()
            self.service.publish_owner(state,force=True)
            opening=self.ledger.get('opening_pending')or{}
            if state.get('world_session')!=c.world or state.get('connected')is not True:
                for key in ('opening_pending','cleanup_pending'):
                    if self.ledger.get(key):
                        self.ledger['receipts'].append(self.ledger[key]|{'outcome':'original_world_ended_control_abandoned','world_goal_completed':False})
                        self.ledger[key]=None
                write_json(self.ledger_path,self.ledger)
                self.stop_result={'released':True,'unknown':self.has_unknown(),'reason':'WORLD_SESSION_CHANGED','game_goal_completed':False}
                return
            released_receipt=next((row for row in reversed(self.ledger['receipts']) if row.get('op')=='material_job_pause'
                and (row.get('params')or{}).get('release')is True and (row.get('receipt')or{}).get('phase')=='done'),None)
            lease=state.get('supervision_lease')or{}
            if (released_receipt is not None and released_receipt.get('world_session')==c.world
                    and state.get('last_request')==released_receipt['receipt'].get('id')
                    and lease.get('job_session')!=c.task and state.get('fisher_active')is False and state.get('navigating')is False):
                if opening:self.ledger['receipts'].append(opening|{'outcome':'exact_session_scope_released_not_world_goal','release_request':state['last_request']})
                self.ledger['opening_pending']=None;write_json(self.ledger_path,self.ledger)
                self.stop_result={'released':True,'unknown':self.has_unknown(),'reason':reason,'game_goal_completed':False}
                return
            if opening and self.owns(state) and not self.ledger.get('cleanup_pending'):
                if self.stop_result is not None and not any(row.get('op')=='material_job_pause' for row in self.ledger['receipts']):self.stop_result=None
                if self.stop_result is None:self.stop(reason,normal=False)
            elif self.ledger.get('cleanup_pending'):
                pending=self.ledger['cleanup_pending'];rid=(pending.get('request_envelope')or{}).get('request_id');path=Path(c.root)/('reply-'+str(rid)+'.json')
                receipt=read(path)if path.is_file()else{}
                lease=state.get('supervision_lease')or{}
                if (receipt.get('id')==rid and receipt.get('phase')=='done' and receipt.get('world_session')==c.world
                        and lease.get('job_session')!=c.task and state.get('fisher_active')is False and state.get('navigating')is False):
                    for key in ('opening_pending','cleanup_pending'):
                        if self.ledger.get(key):
                            self.ledger['receipts'].append(self.ledger[key]|{'outcome':'exact_session_scope_released_not_world_goal','release_request':rid})
                            self.ledger[key]=None
                    write_json(self.ledger_path,self.ledger)
                    self.stop_result={'released':True,'unknown':self.has_unknown(),'reason':reason,'game_goal_completed':False}
            else:
                rid=(opening.get('request_envelope')or{}).get('request_id');path=Path(c.root)/('reply-'+str(rid)+'.json')
                receipt=read(path)if path.is_file()else{}
                if (receipt.get('id')==rid and receipt.get('phase')=='error' and receipt.get('world_session')==c.world
                        and state.get('supervision_lease')==(self.opening_state or{}).get('supervision_lease')):
                    self.ledger['receipts'].append(opening|{'outcome':'exact_session_rejected_not_world_goal','receipt':receipt})
                    self.ledger['opening_pending']=None;write_json(self.ledger_path,self.ledger)
                    self.stop_result={'released':True,'unknown':self.has_unknown(),'reason':reason,'game_goal_completed':False}
            observation={k:state.get(k)for k in ('world_session','control_revision','phase','last_request','health')}
            if observation!=previous:
                self.ledger['opening_wait']={'reason':reason,'observation':observation,'heartbeat_retained':True,'request_replayed':False}
                write_json(self.ledger_path,self.ledger);previous=observation
            if self.ledger.get('opening_pending')or self.ledger.get('cleanup_pending'):time.sleep(.05)
    def stop(self,reason,*,normal=False):
        if self.stop_result is not None:return deepcopy(self.stop_result)
        self.cleaning=True
        if self.backend:self.backend.cleaning=True
        c=self.client;released=c is None
        try:
            state=self.service.observer()
            opening=self.ledger.get('opening_pending')
            if opening and c is not None and getattr(c,'task',None) and getattr(c,'heartbeat',None) is not None:
                # Publishing a session mailbox and observing its admission are
                # separate frames. Never declare release against the old park
                # while the exact new request can still claim the native lease.
                rid=(opening.get('request_envelope')or{}).get('request_id');deadline=time.monotonic()+3
                while True:
                    if self.owns(state):break
                    if state.get('world_session')!=c.world or state.get('connected')is not True:break
                    receipt_path=Path(c.root)/('reply-'+str(rid)+'.json')
                    if receipt_path.is_file():
                        receipt=read(receipt_path)
                        if receipt.get('id')==rid and receipt.get('world_session')==c.world and receipt.get('phase')=='error':
                            opening.update(receipt={k:receipt.get(k)for k in ('id','phase','time','detail')},outcome='session_rejected_not_world_goal')
                            self.ledger['receipts'].append(deepcopy(opening));self.ledger['opening_pending']=None
                            write_json(self.ledger_path,self.ledger);break
                    if time.monotonic()>=deadline:break
                    time.sleep(.05);state=self.service.observer()
            if c is not None and not getattr(c,'task',None) and getattr(c,'heartbeat',None) is None:
                # The constructor's only native pre-lease operation is its
                # read-only parking-column scan. It owns no game inputs and
                # must leave the prior parking controller untouched.
                opening=self.opening_state or {};lease=state.get('supervision_lease')or{}
                released=bool(not self.has_unknown() and state.get('world_session')==opening.get('world_session')
                    and state.get('control_revision')==opening.get('control_revision')
                    and lease==opening.get('supervision_lease') and lease.get('kind')=='parking'
                    and state.get('navigating')is False and state.get('fisher_active')is False
                    and (state.get('menu')or{}).get('cursor',{}).get('count')==0)
            if c is not None and hasattr(c,'task') and c.heartbeat is not None:
                if self.owns(state):
                    c.rev=state['control_revision']  # Only the exact owned envelope can authorize this adoption.
                    self.service.publish_owner(state,force=True)
                    if normal and not self.has_unknown():
                        if self.job=='fish' and state.get('fisher_active') is True:self._send('fisher_stop',cleanup=True)
                        # The ordinary protected finish may move to the registered high park.
                        # Keep priority checks active there; only one-shot cancellation suppresses them.
                        self.cleaning=False
                        if self.backend:self.backend.cleaning=False
                        c.finish();after=self.service.observer();lease=after.get('supervision_lease') or {}
                        released=lease.get('kind')=='parking' and lease.get('id')==c.heartbeat.id and after.get('fisher_active') is False
                    else:
                        if self.job=='fish' and state.get('fisher_active') is True and state.get('screen')=='' and state.get('guard_busy') is False:
                            self._send('fisher_stop',cleanup=True)
                        self._send('material_job_pause',cleanup=True,release=True)
                        after=self.service.observer();lease=after.get('supervision_lease') or {}
                        released=lease.get('job_session')!=c.task and after.get('fisher_active') is False and after.get('navigating') is False
                        if released and self.ledger.get('opening_pending'):
                            self.ledger['receipts'].append(self.ledger['opening_pending']|{'outcome':'session_admitted_then_scoped_release_not_world_goal'})
                            self.ledger['opening_pending']=None;write_json(self.ledger_path,self.ledger)
                else:
                    lease=state.get('supervision_lease') or {}
                    released=(not self.ledger.get('opening_pending') and (state.get('world_session')!=getattr(c,'world',None)
                              or lease.get('job_session')!=c.task and state.get('fisher_active') is False)
                              )
        finally:
            if c is not None:
                if getattr(c,'heartbeat',None) and not self.ledger.get('opening_pending'):c.heartbeat.close()
                if getattr(c,'job_progress',None):c.job_progress.close()
            if self.lock is not None:fcntl.flock(self.lock,fcntl.LOCK_UN);self.lock.close();self.lock=None
            if self.field_context is not None:
                context=self.field_context;self.field_context=None;context.__exit__(None,None,None)
        if self.stop_result is None:
            self.stop_result={'released':released,'unknown':self.has_unknown(),'reason':reason,'game_goal_completed':False}
        return deepcopy(self.stop_result)
