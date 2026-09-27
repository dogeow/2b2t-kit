"""Scoped, reversible access to otherwise sealed construction compartments.

The schematic stays unchanged. Real block scans, inventory deltas and the
native printer batch gate are required before any doorway can count restored.
"""
from collections import Counter
import json
import math
from pathlib import Path
import time

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_cleanup import register, complete
from material_client import Handoff
from .protocol import JobBlocked, JobPaused, server_key
from .construction_access_journal import AccessJournal, journal_path
from .construction_access_plan import (
    AccessPlanBlocked, plan_access, Space, flood, route, point, item, traversable,
)

AIR = {'Block{minecraft:air}', 'Block{minecraft:cave_air}', 'Block{minecraft:void_air}'}
HOSTILES = {'minecraft:'+name for name in (
    'zombie','husk','drowned','skeleton','stray','bogged','wither_skeleton','creeper',
    'spider','cave_spider','witch','pillager','vindicator','ravager','evoker','vex')}


def _scan(c, low, high):
    if math.prod(high[i]-low[i]+1 for i in range(3)) > 50000:
        raise JobBlocked('临时入口核验范围过大，不能用不完整扫描施工')
    reply = c.request('scan', min=low, max=high, details=True)
    if (reply.get('phase') not in (None,'done') or reply.get('world_session') != c.world
            or not isinstance(reply.get('blocks'), list)):
        raise JobBlocked('临时入口扫描未完整确认')
    return reply['blocks']


def _model(c):
    state = c.status()
    if min(state.get('projection_model_protocol',0),state.get('projection_batch_protocol',0)) < 1:
        raise JobBlocked('内腔施工需要更新支持分批坐标的 Kit 主包')
    reply = c.request('projection_model')
    model = reply.get('projection_model') or {}
    if (reply.get('world_session') != c.world or not model.get('content_hash')
            or model.get('loaded_chunks_verified') is not True
            or not isinstance(model.get('expected'),list)
            or model.get('placement_key') != state.get('projection_selection',{}).get('key')):
        raise JobBlocked('无法核对当前完整模型，不能临时拆开外壳')
    return model


def _scope(c, model):
    state=c.status()
    return {'server':server_key(state['server']),'dimension':state['dimension'],
            'placement_key':model['placement_key'],'model_hash':model['content_hash'],
            'world_session':c.world}


def _volume(c, model):
    low=[v-2 for v in model['bounds']['min']]
    high=[v+2 for v in model['bounds']['max']]
    rows=_scan(c,low,high)
    return {'complete':True,'min':low,'max':high,'blocks':rows,
            'world_session':c.world,'observed_at':c.status()['time'],'player':c.status()['pos']}


def _cell(pos):
    # Collision-resolved feet can be a few ten-thousandths below an integer.
    return (math.floor(pos[0]),math.floor(pos[1]+.005),math.floor(pos[2]))


def _safe(c, selection_key):
    state=c.status()
    if (state.get('health',0)<19 or state.get('food',0)<10 or state.get('under_water')
            or not state.get('guard_armed') or not state.get('guard_pve_only')
            or state.get('safety_hold',{}).get('active')
            or state.get('projection_selection',{}).get('key') != selection_key):
        raise JobBlocked('施工入口的生命、防护或投影状态已变化')
    return state


def _nearby_threats(state, bounds):
    return [e for e in state.get('entities',[]) if e.get('type') in HOSTILES
            and len(e.get('pos',[]))==3
            and all(bounds['min'][i]-8 <= e['pos'][i] <= bounds['max'][i]+8 for i in range(3))]


class AccessWork:
    def __init__(self, owner, model, journal):
        self.owner,self.c,self.model,self.journal=owner,owner.ensure_client(),model,journal
        self.plan=journal.data['plan']['access_plan']
        self.key=model['placement_key']
        self.cleanup_key='construction-access:'+str(journal.path)
        register(self.c,self.cleanup_key,self.restore)

    def observations(self):
        blocks=self.journal.data['plan']['blocks']
        low=[min(b['pos'][i] for b in blocks) for i in range(3)]
        high=[max(b['pos'][i] for b in blocks) for i in range(3)]
        rows={tuple(r['pos']):r for r in _scan(self.c,low,high)}
        result=[]
        for b in blocks:
            r=rows.get(tuple(b['pos']))
            result.append({'pos':b['pos'],'state':r['state'] if r else 'Block{minecraft:air}',
                           'fluid':bool(r.get('fluid')) if r else False,
                           'container':bool(r.get('block_entity')) if r else False})
        return {'fresh':True,'exact':True,'world_session':self.c.world,'blocks':result,
                'observed_at':self.c.status()['time']}

    def validate(self):
        _safe(self.c,self.key)
        observations=self.observations()
        self.journal.revalidate(self.c.world,observations)
        return observations

    def verify_model(self):
        current=_model(self.c)
        if current['content_hash']!=self.model['content_hash']:
            raise JobBlocked('图纸内容已经改变，保留施工入口记录并停止，不沿用旧施工方案')

    def proof(self):
        return {'world_session':self.c.world,'observations':self.observations(),
                'inventory':{'counts':dict(inventory_counts(self.c.status()))}}

    def dispatch(self, kind, op, data=None, **params):
        self.validate()
        self.journal.intent(kind,world_session=self.c.world,**(data or {}))
        previous=self.c.last
        try:
            reply=self.c.request(op,**params)
        except BaseException:
            if self.c.last and self.c.last!=previous:self.journal.record_request(self.c.last)
            raise
        if self.c.last and self.c.last!=previous:self.journal.record_request(self.c.last)
        if reply.get('phase')!='done':
            raise JobBlocked('施工入口动作未确认，不会重复发送：'+str(reply.get('detail',op)))
        return reply

    def pause(self):
        state=self.c.status();job=state.get('build_job') or {}
        if job.get('active'):
            self.c.checked('build_control',job_session=job['session'],action='pause_and_report')
        deadline=time.monotonic()+5
        while True:
            state=self.c.status()
            if (not state.get('build_job',{}).get('active')
                    and state.get('build_job',{}).get('queue_settled',True)
                    and not state.get('professional_printer',{}).get('waiting_for_server')):return
            if time.monotonic()>=deadline:raise JobBlocked('打印队列尚未确认停稳，保留入口记录')
            time.sleep(.15)

    def mask(self, targets=None, floor=None):
        self.pause()
        if targets is None:
            reply=self.c.checked('projection_batch_clear',placement_key=self.key)
            scope=reply.get('projection_batch') or {}
            if scope.get('active') is not False or scope.get('count')!=0 or scope.get('min_feet_y') is not None:
                raise JobBlocked('本批施工坐标限制尚未确认解除，不能宣布入口收尾完成')
            return
        positions=[r['pos'] for r in targets]
        reply=self.c.checked('projection_batch_set',placement_key=self.key,positions=positions,
                             **({'min_feet_y':floor} if floor is not None else {}))
        scope=reply.get('projection_batch') or {}
        if (scope.get('active') is not True or scope.get('count')!=len(positions)
                or scope.get('placement_key')!=self.key
                or floor is not None and scope.get('min_feet_y')!=floor):
            raise JobBlocked('本批允许施工坐标未得到原生确认')

    def move(self, path):
        from .navigation import _air_move
        previous=None
        for raw in path:
            self.owner.checkpoint();state=_safe(self.c,self.key)
            # 0.17 feet offset fits inside a two-block doorway and leaves a
            # margin for the small gravity impulse after Flight restoration.
            target=[raw[0],raw[1]+.15,raw[2]]
            if (previous is not None and abs(raw[1]-previous[1])<.01
                    and math.hypot(raw[0]-previous[0],raw[2]-previous[2])>.01):
                # On a planned horizontal leg, keep the measured Y. Raising
                # towards the nominal waypoint under a low ceiling can exceed
                # the two-cell gap before Flight has finished braking.
                target[1]=state['pos'][1]
            previous=raw
            if math.dist(state['pos'],target)<.15:continue
            current=state['pos']
            low=[math.floor(min(current[0],target[0])-.31),math.floor(min(current[1],target[1])+.005),
                 math.floor(min(current[2],target[2])-.31)]
            high=[math.floor(max(current[0],target[0])+.31),math.floor(max(current[1],target[1])+1.82),
                  math.floor(max(current[2],target[2])+.31)]
            rows=_scan(self.c,low,high)
            if any(not traversable(r) for r in rows):
                raise JobBlocked('施工入口实际通道已改变，不沿旧规划穿墙')
            _air_move(self.c,target,120)

    def path_to(self, target):
        volume=_volume(self.c,self.model)
        space=Space(volume['min'],volume['max'],volume['blocks'],100000)
        parent=flood(space.free(space.blocked),_cell(self.c.status()['pos']))
        return route(parent,_cell(target))

    def side_distance(self):
        portal=self.journal.data['plan']['blocks'][0]['pos']
        center=[portal[0]+.5,portal[1],portal[2]+.5]
        normal=[self.plan['outside_station'][i]-center[i] for i in (0,2)]
        position=self.c.status()['pos']
        return sum((position[i]-center[i])*normal[k] for k,i in enumerate((0,2)))

    def outside(self):return self.side_distance()>.82

    def cross(self, entering):
        """Align outside the lintel, then cross at the *observed* feet height.

        Restoring a user's Flight settings can lower a completed waypoint by
        about 0.2 blocks. A requested Y alone therefore cannot prove doorway
        clearance. Never expand collision tolerances to mask that difference.
        """
        from .navigation import _air_move
        start=self.plan['outside_station'] if entering else self.plan['inside_station']
        destination=self.plan['inside_station'] if entering else self.plan['outside_station']
        floor=min(b['pos'][1] for b in self.journal.data['plan']['blocks'])
        target_y=floor+.35
        for _ in range(3):
            state=_safe(self.c,self.key);current=state['pos']
            target=[start[0],target_y,start[2]]
            low=[math.floor(min(current[0],target[0])-.31),math.floor(min(current[1],target[1])),math.floor(min(current[2],target[2])-.31)]
            high=[math.floor(max(current[0],target[0])+.31),math.floor(max(current[1],target[1])+1.82-1e-6),math.floor(max(current[2],target[2])+.31)]
            if any(not traversable(r) for r in _scan(self.c,low,high)):
                raise JobBlocked('门外校准位置没有足够净空，不能穿过门楣')
            _air_move(self.c,target,35)
            actual=self.c.status()['pos']
            if floor+.01<=actual[1]<=floor+.18 and math.hypot(actual[0]-start[0],actual[2]-start[2])<.12:
                break
            target_y+=floor+.10-actual[1]
        else:raise JobBlocked('实际脚部高度未稳定在门洞净空内，停止跨越')
        target=[destination[0],actual[1],destination[2]]
        low=[math.floor(min(actual[0],target[0])-.31),math.floor(actual[1]),math.floor(min(actual[2],target[2])-.31)]
        high=[math.floor(max(actual[0],target[0])+.31),math.floor(actual[1]+1.82-1e-6),math.floor(max(actual[2],target[2])+.31)]
        if any(not traversable(r) for r in _scan(self.c,low,high)):
            raise JobBlocked('门洞的实时身体通道仍有阻挡，不继续移动')
        _air_move(self.c,target,35)
        if (self.side_distance()>=-.82 if entering else not self.outside()):
            raise JobBlocked('角色尚未完全越过施工入口')
        self.journal.checkpoint('inside' if entering else 'outside',world_session=self.c.world,
                               actual_position=self.c.status()['pos'])

    def reconcile(self):
        pending=self.journal.pending
        if pending is None:return
        self.verify_model();observations=self.validate()
        data=pending.get('data',{});pos=data.get('pos')
        block=next((b for b in self.journal.data['plan']['blocks'] if b['pos']==pos),None)
        if block is None:raise JobBlocked('入口未确认动作缺少已登记坐标')
        actual=next(r['state'] for r in observations['blocks'] if r['pos']==pos)
        if pending['kind']=='open_block' and actual in AIR:
            from .construction_access_receipts import find_removal_receipt
            receipt=find_removal_receipt(self.c.root,pending,block)
            if receipt is not None:
                self.journal.confirm('open_block',**self.proof(),removed=True,recovered=False,
                    prior_native_event=receipt['native_event'],owned_drop_ids=receipt['owned_drop_ids'])
                return
        if (pending['kind']=='restore_block' and actual==block['expected']
                and type(data.get('before_count')) is int
                and inventory_counts(self.c.status()).get(block['item'],0)==data['before_count']-1):
            self.journal.confirm('restore_block',**self.proof(),placed=1,reconciled_from_current_state=True)
            return
        raise JobBlocked('施工入口动作结果仍不明确；保留记录，不重复挖放')

    def opening_baseline(self):
        record=self.journal.data
        prior=next((r['data'] for r in record['checkpoints'] if r['stage']=='opening'),None)
        if prior is not None:return prior
        state=self.c.status();held=inventory_counts(state)
        before={name:held.get(name,0) for name in self.plan['restore_reserve']}
        known=set()
        for op in record['operations']:
            if op['kind']=='open_block':
                d=op['data'];before[d['item']]=min(before[d['item']],d['before_count'])
                known.update(op.get('evidence',{}).get('owned_drop_ids',[]))
        for e in state.get('entities',[]):
            if (e.get('type')=='minecraft:item' and e.get('stack',{}).get('item') in before
                    and e.get('uuid') not in known and len(e.get('pos',[]))==3
                    and any(math.dist(e['pos'],b['pos'])<5 for b in record['plan']['blocks'])):
                raise JobBlocked('入口附近有归属未确认的同类掉落，先核对再继续')
        baseline={'before':before,'before_drop_ids':[e['uuid'] for e in state.get('entities',[])
                  if e.get('type')=='minecraft:item' and e.get('uuid') not in known]}
        self.journal.checkpoint('opening',world_session=self.c.world,**baseline)
        return baseline

    def collect_opening(self):
        record=self.journal.data
        baseline=next((r['data'] for r in record['checkpoints'] if r['stage']=='opening'),None)
        if baseline is None:return
        wanted=Counter(baseline['before'])
        known=set()
        for op in record['operations']:
            if op['kind']=='open_block' and op.get('evidence',{}).get('removed'):wanted[op['data']['item']]+=1
            if op['kind']=='restore_block' and op.get('evidence',{}).get('placed')==1:wanted[op['data']['item']]-=1
            known.update(op.get('evidence',{}).get('owned_drop_ids',[]))
        deadline=time.monotonic()+8
        while True:
            state=_safe(self.c,self.key);held=inventory_counts(state)
            if any(held.get(i,0)>n for i,n in wanted.items()):raise JobBlocked('入口掉落数量超出预期，先核对物品归属')
            drops=[e for e in state.get('entities',[]) if e.get('type')=='minecraft:item'
                   and e.get('uuid') not in baseline['before_drop_ids']
                   and e.get('stack',{}).get('item') in wanted and len(e.get('pos',[]))==3
                   and (any(math.dist(e['pos'],b['pos'])<6 for b in record['plan']['blocks'])
                        or e.get('uuid') in known and all(self.model['bounds']['min'][i]-2<=e['pos'][i]
                            <=self.model['bounds']['max'][i]+2 for i in range(3)))]
            if all(held.get(i,0)==n for i,n in wanted.items()):
                if not drops:
                    self.journal.checkpoint('drops_recovered',world_session=self.c.world,inventory=dict(held),wanted=dict(wanted));return
                if time.monotonic()>=deadline:raise JobBlocked('背包数量已到，但入口掉落仍在世界，等待物品同步核验')
                time.sleep(.15);continue
            if drops:
                from drop_collection import collect_drop
                drop=min(drops,key=lambda e:math.dist(e['pos'],state['pos']))
                if not collect_drop(self.c,drop,observation=state,seconds=25):
                    raise JobBlocked('完整入口已打开，但掉落仍未收回，保留回收记录')
            if time.monotonic()>=deadline:raise JobBlocked('两格入口掉落尚未全部核对')
            time.sleep(.15)

    def open(self):
        self.verify_model()
        self.reconcile()
        self.mask([])
        reserve=self.plan['restore_reserve'];held=inventory_counts(self.c.status())
        if any(held.get(i,0)<n for i,n in reserve.items()):
            raise JobBlocked('没有足够的封口备用材料，暂不开施工入口')
        from .acquisition import _travel
        if math.dist(self.c.status()['pos'],self.plan['outside_station'])<1:
            self.move([self.plan['outside_station']])
        else:
            _travel(self.c,self.plan['approach_anchor'],self.owner.checkpoint,[])
            self.move(self.plan['approach_path'])
        tools=[r for r in self.c.status()['inventory'] if 0<=r.get('slot',-1)<36
               and r.get('item') in ('minecraft:diamond_pickaxe','minecraft:netherite_pickaxe')
               and r.get('durability',0)>=64]
        if not tools:raise JobBlocked('施工入口需要耐久充足的镐')
        tool=max(tools,key=lambda r:r['durability'])
        self.c.checked('select_item',item=tool['item'],slot=tool['slot'])
        baseline=self.opening_baseline()
        blocks={tuple(b['pos']):b for b in self.journal.data['plan']['blocks']}
        for pos in self.plan['mine_order']:
            self.verify_model()
            block=blocks[tuple(pos)];state=self.c.status();before=inventory_counts(state).get(block['item'],0)
            actual=next(r['state'] for r in self.validate()['blocks'] if r['pos']==pos)
            if actual in AIR:
                if not any(op['kind']=='open_block' and op['data'].get('pos')==pos and op.get('evidence',{}).get('removed')
                           for op in self.journal.data['operations']):
                    raise JobBlocked('门洞在本任务确认破坏之前已变化，不能当成自己的开洞动作')
                continue
            self.dispatch('open_block','mine_block',{'pos':pos,'before_count':before,'item':block['item']},
                          pos=pos,expected_state=block['expected'],face=self.plan['outside_face'],seconds=20)
            if any(r['pos']==pos and r['state'] not in AIR for r in self.observations()['blocks']):
                raise JobBlocked('临时门洞未得到实际空气确认')
            self.journal.confirm('open_block',**self.proof(),removed=True,recovered=False,
                owned_drop_ids=[e['uuid'] for e in self.c.status().get('entities',[]) if e.get('type')=='minecraft:item'
                                and e.get('uuid') not in baseline['before_drop_ids']
                                and e.get('stack',{}).get('item')==block['item']
                                and len(e.get('pos',[]))==3 and math.dist(e['pos'],pos)<6])
        # A one-block notch is not a player-sized pickup path. Open both
        # registered blocks before entering and confirming their combined loot.
        self.cross(True)
        self.collect_opening()
        self.journal.checkpoint('entered',world_session=self.c.world)

    def construct(self):
        from goal_workflow import build_phase, subset_matches
        completed=0
        for stage in self.plan['stages']:
            self.owner.checkpoint()
            self.verify_model()
            state=_safe(self.c,self.key)
            low=[min(r['pos'][i] for r in stage['targets']) for i in range(3)]
            high=[max(r['pos'][i] for r in stage['targets']) for i in range(3)]
            if subset_matches(_scan(self.c,low,high),stage['targets']):
                completed+=len(stage['targets'])
                self.journal.checkpoint('layer_revalidated',world_session=self.c.world,layer_y=stage['layer_y'],count=completed)
                continue
            if _nearby_threats(state,self.model['bounds']):
                raise JobBlocked('内腔通道附近有怪物，保持入口并先处理防护')
            raised=list(stage['station']);raised[1]+=1
            try:path=self.path_to(raised)
            except AccessPlanBlocked:path=self.path_to(stage['station'])
            self.move(path)
            if self.c.status()['pos'][1]<stage['layer_y']+1-.08:
                raise JobBlocked('角色尚未站到本层上方，不开始封层')
            self.verify_model()
            self.mask(stage['targets'],stage['layer_y']+1)
            after=build_phase(self.c,self.key,seconds=240,stall_seconds=40,
                              complete_cells=stage['targets'],background=True)
            self.owner.audit,self.owner.audit_dirty=after,False
            if not subset_matches(_scan(self.c,low,high),stage['targets']):
                raise JobBlocked('本层内饰尚未实际完成，停止继续封层')
            if self.c.status()['pos'][1]<stage['layer_y']+1-.08:
                raise JobBlocked('本层结束位置不在已核验的一侧，保留入口')
            completed+=len(stage['targets'])
            self.journal.checkpoint('layer_completed',world_session=self.c.world,layer_y=stage['layer_y'],count=completed)
            self.mask([])
        return completed

    def restore(self):
        if self.journal.restored:
            complete(self.c,self.cleanup_key);return
        self.verify_model()
        self.pause();self.reconcile();observations=self.validate()
        data=self.journal.data;position=self.c.status()['pos'];bounds=self.model['bounds']
        unopened=(data['stage']=='planned' and not data['operations']
                  and all(r['state']==next(b['expected'] for b in data['plan']['blocks'] if b['pos']==r['pos'])
                          for r in observations['blocks'])
                  and not all(bounds['min'][i]-.31<=position[i]<=bounds['max'][i]+1.31 for i in range(3)))
        if unopened:
            self.mask(None);self.journal.checkpoint('restored',**self.proof(),outside_position=position)
            complete(self.c,self.cleanup_key);return
        self.collect_opening()
        self.mask([])
        if not self.outside():
            self.move(self.path_to(self.plan['inside_station']))
            self.cross(False)
        self.journal.checkpoint('outside',world_session=self.c.world,position=self.c.status()['pos'])
        blocks={tuple(b['pos']):b for b in self.journal.data['plan']['blocks']}
        for pos in self.plan['restore_order']:
            block=blocks[tuple(pos)];observations=self.validate()
            actual=next(r['state'] for r in observations['blocks'] if r['pos']==pos)
            if actual==block['expected']:continue
            if actual not in AIR:raise JobBlocked('原入口出现其它方块，不覆盖玩家更改')
            support=[pos[0],pos[1]-1,pos[2]];rows=_scan(self.c,support,support)
            if len(rows)!=1 or not rows[0].get('solid') or rows[0].get('fluid') or rows[0].get('block_entity'):
                raise JobBlocked('封回入口的支撑方块已改变')
            before=inventory_counts(self.c.status()).get(block['item'],0)
            if before<1:raise JobBlocked('入口封回材料不足，保留缺口记录')
            self.c.checked('select_item',item=block['item'])
            self.dispatch('restore_block','interact',{'pos':pos,'item':block['item'],'before_count':before},
                          pos=support,face='up',expected_state=rows[0]['state'],expected_hand=block['item'])
            observed=self.observations()
            if (next(r['state'] for r in observed['blocks'] if r['pos']==pos)!=block['expected']
                    or inventory_counts(self.c.status()).get(block['item'],0)!=before-1):
                raise JobBlocked('入口封回的方块或物品数量未确认，不重复放置')
            self.journal.confirm('restore_block',**self.proof(),placed=1)
        self.mask(None)
        self.journal.checkpoint('restored',**self.proof(),outside_position=self.c.status()['pos'])
        complete(self.c,self.cleanup_key)


def _index(owner):return owner.root.parent/'construction-access'


def recover_pending(owner):
    """Before travel, resume only cleanup of a scoped, freshly checked doorway."""
    c=owner.ensure_client()
    if not _index(owner).exists():return
    state=c.status();key=state.get('projection_selection',{}).get('key')
    records=[]
    paths=list(_index(owner).glob('*/*/access.json'))+list(_index(owner).glob('*/*/*/access.json'))
    for path in paths:
        data=json.loads(path.read_text());scope=data.get('scope',{})
        if (data.get('stage')!='restored' and scope.get('server')==server_key(state['server'])
                and scope.get('dimension')==state['dimension']):
            if scope.get('placement_key')!=key:raise JobBlocked('另一投影仍有未封施工入口，先恢复原投影')
            records.append(path)
    if not records:return
    if len(records)>1:raise JobBlocked('存在多份未封入口记录，需要先核对')
    model=_model(c);journal=AccessJournal(records[0],_scope(c,model))
    work=AccessWork(owner,model,journal);work.validate();work.reconcile()
    if any(op['kind']=='open_block' for op in journal.data['operations']) and not any(
            row['stage']=='entered' for row in journal.data['checkpoints']):
        work.open()
    request=getattr(owner,'request',{})
    if request.get('mode')=='projection' and request.get('projection_key')==model['placement_key']:
        targets=[row for stage in work.plan['stages'] for row in stage['targets']]
        if targets:
            low=[min(r['pos'][i] for r in targets) for i in range(3)]
            high=[max(r['pos'][i] for r in targets) for i in range(3)]
            cells={tuple(row['pos']):row['state'] for row in _scan(c,low,high)}
            needed=Counter(item(row['expected']) for row in targets if cells.get(tuple(row['pos']))!=row['expected'])
            held=inventory_counts(c.status())
            if all(held.get(name,0)>=count for name,count in needed.items()):
                work.construct()
    work.restore()


def attempt(owner, audit):
    c=owner.ensure_client();state=c.status()
    if min(state.get('projection_model_protocol',0),state.get('projection_batch_protocol',0))<1:return None
    model=_model(c)
    if audit.get('placement_key')!=model['placement_key'] or audit.get('loaded_chunks_verified') is not True:return None
    if _nearby_threats(_safe(c,model['placement_key']),model['bounds']):return None
    volume=_volume(c,model)
    try:
        plan=plan_access(volume,model['expected'],state['projection_selection'],audit['mismatches'],
                         dict(inventory_counts(c.status())),start_position=c.status()['pos'])
    except AccessPlanBlocked as error:
        write_json(owner.out/'access-unavailable.json',{'reason':str(error),'observed_at':volume['observed_at']})
        return None
    scope=_scope(c,model);path=journal_path(_index(owner),scope)
    if path.exists():
        old=AccessJournal(path,scope)
        if not old.restored:raise JobBlocked('先恢复未完成的施工入口，不能创建第二份')
        path=journal_path(_index(owner),scope,transaction_id='access-'+str(time.time_ns()))
    blocks=[{'pos':b['pos'],'expected':b['expected'],'item':item(b['expected'])} for b in plan['portal']]
    data={'blocks':blocks,'outside':plan['outside_station'],'inside':plan['inside_station'],'access_plan':plan}
    journal=AccessJournal(path,scope,data);work=AccessWork(owner,model,journal)
    work.validate();work.open();count=work.construct();work.restore()
    after=owner.refresh_audit()
    return {'phase':'done','detail':'内腔已分层施工并原样封回入口','placed':after['matched']-audit['matched'],
            'interior_verified':count,'access_journal':str(path)}
