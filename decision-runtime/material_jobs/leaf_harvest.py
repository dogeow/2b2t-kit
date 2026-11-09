"""Bounded continuous shearing through one native Kit material controller."""
import argparse
import hashlib
import json
import math
import time
from collections import Counter
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from native_outcome_fence import RetainedUnknownMaterialClient, never_dispatched_mining
from terminal_confirmation import verified
from work_access import BLOCKED_APPROACHES

LEAVES = frozenset('minecraft:'+n+'_leaves' for n in (
    'oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry',
    'azalea','flowering_azalea','pale_oak'))
PICKUP_REFUSALS = BLOCKED_APPROACHES|{
    'Drop disappeared without inventory confirmation','Drop identity or stack changed',
    'Drop is no longer loaded; observe again','Drop pickup not confirmed at the reached position'}
APPROACH_REFUSALS = BLOCKED_APPROACHES|{'Actual collision on depot route','No visible collision-free work-block approach'}


class LeafStopped(RuntimeError):
    pass


def point(p, integer=False):
    return isinstance(p,list) and len(p)==3 and all(
        type(v) is int if integer else type(v) in (int,float) and math.isfinite(v) for v in p)


def validate(config):
    if not isinstance(config,dict) or config.get('schema')!=1:raise ValueError('Expected leaf job schema 1')
    if not isinstance(config.get('server'),str) or not config['server']:raise ValueError('Explicit server address required')
    if config.get('dimension')!='minecraft:overworld':raise ValueError('Overworld leaf job required')
    if type(config.get('target')) is not int or not 1<=config['target']<=1000000:raise ValueError('Invalid target')
    if config.get('target_scope','total_stock') not in ('total_stock','new_collected'):raise ValueError('Invalid target scope')
    if not point(config.get('park_target')):raise ValueError('Verified native high park required')
    regions=config.get('regions')
    if not isinstance(regions,list) or not 1<=len(regions)<=64:raise ValueError('Need 1..64 authorized regions')
    for r in regions:
        if not isinstance(r,dict) or r.get('authorized') is not True or not point(r.get('min'),True) or not point(r.get('max'),True):raise ValueError('Explicit integer source bounds required')
        if any(a>b or b-a>31 for a,b in zip(r['min'],r['max'])) or math.prod(b-a+1 for a,b in zip(r['min'],r['max']))>50000:raise ValueError('Region exceeds native bounded scan')
        if not -64<=r['min'][1]<=r['max'][1]<=319:raise ValueError('Region outside world height')
    for r in config.get('protected_regions',[]):
        if not point(r.get('min'),True) or not point(r.get('max'),True) or any(a>b for a,b in zip(r['min'],r['max'])):raise ValueError('Invalid protected region')
    if any(not point(p,True) for p in config.get('depots',[])):raise ValueError('Invalid designated leaf depot')
    if config.get('execution','serial') not in ('serial','native_burst'):raise ValueError('Invalid leaf execution mode')
    for key,default,low,high in (('reserve_slots',2,1,10),('batch_size',12,1,32 if config.get('execution')=='native_burst' else 16),('approach_seconds',12,4,30)):
        if type(config.get(key,default)) is not int or not low<=config.get(key,default)<=high:raise ValueError('Invalid '+key)
    grace=config.get('pickup_grace_seconds',.5)
    if type(grace) not in (int,float) or not math.isfinite(grace) or not 0<=grace<=3:raise ValueError('Invalid pickup grace')
    return config


def inside(p,r):return all(a<=v<=b for v,a,b in zip(p,r['min'],r['max']))
def leaf_id(row):return row.get('state','').split('}',1)[0].removeprefix('Block{')
def natural_leaf(row):
    return (leaf_id(row) in LEAVES and 'persistent=false' in row.get('state','')
            and 'waterlogged=false' in row.get('state','') and row.get('fluid') is False
            and row.get('block_entity') is False and point(row.get('pos'),True))
def leaf_counts(state):return {i:n for i,n in inventory_counts(state).items() if i in LEAVES and n}
def shears(state):
    return max((r for r in state.get('inventory',[]) if r.get('item')=='minecraft:shears'
                and type(r.get('slot')) is int and 0<=r['slot']<36 and r.get('count')==1
                and type(r.get('durability')) is int and r['durability']>=2),
               key=lambda r:r['durability'],default=None)
def center(row):return [v+.5 for v in row['pos']]
def face_from(pos,row):
    delta=[a-b for a,b in zip([pos[0],pos[1]+1.62,pos[2]],center(row))]
    axis=max(range(3),key=lambda i:abs(delta[i]))
    return (('west','east'),('down','up'),('north','south'))[axis][delta[axis]>=0]
def reach_distance(pos,row):
    aim=center(row);face=face_from(pos,row)
    axis,offset={'west':(0,-.5),'east':(0,.5),'down':(1,-.5),'up':(1,.5),'north':(2,-.5),'south':(2,.5)}[face]
    aim[axis]+=offset
    return math.dist([pos[0],pos[1]+1.62,pos[2]],aim)
def capacity(state,item,reserve):
    slots=[r for r in state.get('inventory',[]) if 0<=r.get('slot',99)<36]
    if len(slots)!=36:raise LeafStopped('Incomplete inventory; no capacity credit')
    free=sum(not r.get('count') for r in slots)
    return sum(64-r['count'] for r in slots if r.get('item')==item)+max(0,free-reserve)*64


def collect_leaf_drop(client,drop,state):
    """One native pickup per identity; batch accounting handles fresh merges."""
    rec=client.request('collect_item',expected_uuid=drop['uuid'],expected_item=drop['stack']['item'],
                       expected_count=drop['stack']['count'],seconds=20)
    return rec.get('phase')=='done' and rec.get('id')==client.last and rec.get('world_session')==client.world


def pickup_refusal(event,drop,world):
    params=event.get('params') or {}
    return (event.get('world_session')==world and event.get('op')=='collect_item'
            and event.get('phase') in ('waiting','error') and event.get('detail') in PICKUP_REFUSALS
            and params.get('expected_uuid')==drop.get('uuid')
            and params.get('expected_item')==drop.get('stack',{}).get('item')
            and params.get('expected_count')==drop.get('stack',{}).get('count'))


def retained_batch_refusal(directory,book):
    """Admit only settlement of an exactly terminal previous pickup, never mining."""
    pending=book.get('pending') or {};batch=book.get('batch')
    if not batch:raise LeafStopped('Only an already recorded batch can be reconciled')
    if pending.get('kind')=='native_burst':
        request=pending.get('request') or {};bid=request.get('id')
        if not isinstance(bid,str) or not bid.startswith('leaf-') or request.get('world_session')!=book.get('world'):raise LeafStopped('Native burst identity differs')
        out=Path(directory);root=Path('/Applications/.minecraft/versions/26.2/config/twob2tkit/automation')
        path=out/'native-bursts'/bid/'native-result.json'
        claim=root/'leaf-shear-claims'/(bid+'-result.json')
        if not claim.is_file():raise LeafStopped('Native burst has no durable terminal claim')
        host=json.loads(claim.read_text())
        if path.is_file():result=json.loads(path.read_text())
        else:
            result=json.loads((root/'leaf-shear-state.json').read_text())
            released=json.loads((out/'safe-native-batch-release-result.json').read_text())
            if released.get('native_burst_receipt')!=bid or released.get('phase')!='done' or released.get('guard') is not True:
                raise LeafStopped('Original native owner release is not proven')
            write_json(out/'native-bursts'/bid/'native-result.json',result)
        if not path.is_file():raise LeafStopped('Per-burst receipt could not be retained')
        if (result!=host or result.get('id')!=bid or result.get('world_session')!=book['world']
                or result.get('phase')!='stopped' or result.get('reason')!='shears_changed_or_exhausted'
                or result.get('pending')!=[] or result.get('confirmation')!='vanilla_prediction_retired_and_live_block_observation'):
            raise LeafStopped('Native burst was not terminally reconciled')
        if pending.get('request',{}).get('task_session')!=request.get('task_session'):raise LeafStopped('Native task identity differs')
        return result
    if pending.get('kind')!='batch_pickup':raise LeafStopped('Only a terminal batch refusal can be reconciled')
    root=Path(directory)/'control'
    if (root/'unconfirmed-native-request.json').exists():raise LeafStopped('Original native request may be unknown; retain it')
    events=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines()]
    if not events or not pickup_refusal(events[-1],pending.get('drop',{}),book['world']):raise LeafStopped('No exact terminal pickup refusal for this batch')
    if pending.get('request_id') not in (None,events[-1].get('request_id')):raise LeafStopped('Original pickup identity differs')
    return events[-1]


class LeafHarvester:
    def __init__(self,client,config,directory,*,pickup,deposit,clock=time.monotonic,sleep=time.sleep,resume_batch=False,resume_receipt=None):
        self.c=client;self.config=validate(config);self.out=Path(directory);self.out.mkdir(parents=True,exist_ok=True)
        self.path=self.out/'leaf-progress.json';self.pickup=pickup;self.deposit=deposit;self.clock=clock;self.sleep=sleep
        fingerprint=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest();state=self.c.status()
        if self.path.exists():
            self.book=json.loads(self.path.read_text())
            if self.book.get('fingerprint')!=fingerprint or self.book.get('world')!=self.c.world:raise LeafStopped('Job scope changed; reconcile original journal')
            if self.book.get('pending') or self.book.get('batch'):
                if not resume_batch:raise LeafStopped('Original batch pending; never replay it')
                if self.book.get('pending'):
                    receipt=resume_receipt if resume_receipt is not None else retained_batch_refusal(directory,self.book)
                else:receipt=None
                if self.book.get('pending',{}).get('kind')=='native_burst':
                    if receipt.get('id')!=self.book['pending']['request'].get('id'):raise LeafStopped('Original native batch identity differs')
                    self.book['batch']['mined']=[{'pos':x['pos'],'item':x['item'],'request_id':receipt['id']}for x in receipt['removed']]
                    self.book['metrics']['mined']+=len(receipt['removed'])
                else:
                    if self.book.get('pending'):
                        if not pickup_refusal(receipt,self.book['pending'].get('drop',{}),self.book['world']):raise LeafStopped('Batch receipt differs from original drop')
                        if self.book['pending'].get('request_id') not in (None,receipt.get('request_id')):raise LeafStopped('Original pickup request differs')
                        self.book['batch'].setdefault('attempted_drop_ids',[]).append(self.book['pending']['drop']['uuid'])
                        self.book.setdefault('retained_pickup_receipts',[]).append(receipt)
                    else:
                        limit=Counter(row['item'] for row in self.book['batch'].get('mined',[]))+Counter(self.book.get('outstanding',{}))
                        actual=leaf_counts(state);before=self.book['batch'].get('before',{});delta={k:actual.get(k,0)-before.get(k,0)for k in set(actual)|set(before)}
                        if any(v<0 or v>limit[k]for k,v in delta.items()):raise LeafStopped('Unsettled batch inventory is outside confirmed receipt limits')
                self.book['pending']=None
            elif self.book.get('expected_bag')!=leaf_counts(state):raise LeafStopped('Inventory changed outside this job; reconcile counts')
        else:
            self.book={'schema':1,'fingerprint':fingerprint,'world':self.c.world,'initial_bag':leaf_counts(state),
                       'expected_bag':leaf_counts(state),'collected':0,'gathered':{},'stored':{},'pending':None,'phase':'ready'}
        self.book['execution']='native_continuous_shears_v1' if config.get('execution')=='native_burst' else 'continuous_batch_v2';self.book.setdefault('batch',None)
        self.book.setdefault('outstanding',{});self.book.setdefault('metrics',{'mined':0,'batches':0,'tool_switches':0,'approaches':0})
        self.skipped=set();self.native_remaining=[];self.native_retries=Counter();self.save()

    def progress(self):return self.book['collected']+(sum(self.book['initial_bag'].values()) if self.config.get('target_scope','total_stock')=='total_stock' else 0)
    def save(self):write_json(self.path,self.book)
    def state(self):
        deadline=self.clock()+30
        while True:
            if (self.out/'STOP').exists():raise LeafStopped('Stop requested')
            s=self.c.status()
            if s.get('world_session')!=self.c.world or s.get('manual_movement') or s.get('screen'):raise LeafStopped('Manual input, interface or world changed')
            if s.get('health',0)<19 or s.get('food',0)<18 or s.get('under_water') or s.get('safety_hold',{}).get('active'):raise LeafStopped('Native survival protection takes priority')
            if not s.get('guard_armed') or not s.get('guard_pve_only'):raise LeafStopped('Native protection was disarmed')
            if not s.get('guard_busy'):return s
            if self.clock()>=deadline:raise LeafStopped('Native defense remains busy; no new work sent')
            self.sleep(.1)
    def allowed(self,row):
        return (natural_leaf(row) and any(inside(row['pos'],r) for r in self.config['regions'])
                and not any(inside(row['pos'],r) for r in self.config.get('protected_regions',[])))
    def scan(self,lo,hi):
        self.state();q=self.c.request('scan',min=lo,max=hi,details=True);size=math.prod(b-a+1 for a,b in zip(lo,hi))
        if q.get('phase')!='done' or q.get('world_session')!=self.c.world or q.get('scan_cells_read')!=size or q.get('scan_total_cells')!=size or not isinstance(q.get('blocks'),list):raise LeafStopped('Incomplete live scan')
        seen=set()
        for row in q['blocks']:
            p=row.get('pos')
            if not point(p,True) or tuple(p) in seen or not all(a<=v<=b for v,a,b in zip(p,lo,hi)):raise LeafStopped('Invalid scan coordinates')
            if any(type(row.get(k)) is not bool for k in ('fluid','solid','passable','block_entity')):raise LeafStopped('Missing block facts')
            seen.add(tuple(p))
        return q['blocks']
    def fresh_leaf(self,pos,neighbors=False):
        rows=self.scan([v-1 for v in pos],[v+1 for v in pos]) if neighbors else self.scan(pos,pos)
        if neighbors and any(r.get('fluid') and sum(abs(a-b) for a,b in zip(r['pos'],pos))==1 for r in rows):return None
        return next((r for r in rows if r['pos']==pos and self.allowed(r)),None)
    def ensure_shears(self):
        s=self.state();hand=s.get('hand',{})
        if hand.get('item')=='minecraft:shears' and hand.get('durability',0)>=2:return
        tool=shears(s)
        if tool is None:raise LeafStopped('Usable shears required')
        self.c.checked('select_item',item='minecraft:shears',slot=tool['slot'])
        hand=self.state().get('hand',{})
        if hand.get('item')!='minecraft:shears' or hand.get('durability',0)<2:raise LeafStopped('Shears hand not confirmed')
        self.book['metrics']['tool_switches']+=1
    def credit(self,gains,state):
        self.book['collected']+=sum(gains.values())
        for item,n in gains.items():self.book['gathered'][item]=self.book['gathered'].get(item,0)+n
        self.book['expected_bag']=leaf_counts(state)
    def late_gains(self,state):
        actual=leaf_counts(state);expected=self.book['expected_bag'];gains={}
        for item in set(actual)|set(expected):
            n=actual.get(item,0)-expected.get(item,0)
            if n<0 or n>self.book['outstanding'].get(item,0):raise LeafStopped('Inventory changed beyond confirmed leaf receipts')
            if n:gains[item]=n
        if gains:
            for item,n in gains.items():self.book['outstanding'][item]-=n
            self.credit(gains,state);self.book.setdefault('late_pickups',[]).append({'gains':gains,'time':state.get('time')});self.save()
    def begin_batch(self,state):
        if self.book['pending'] or self.book['batch']:raise LeafStopped('Original batch still pending')
        self.late_gains(state)
        self.book['batch']={'before':leaf_counts(state),'mined':[],
                            'prior_drop_ids':[e['uuid'] for e in state.get('entities',[]) if isinstance(e.get('uuid'),str)],
                            'station':state['pos'],'started_at':state.get('time')}
        self.save()
    def mine(self,row):
        self.ensure_shears();row=self.fresh_leaf(row['pos'],neighbors=True)
        if row is None:return False  # Decay is an ordinary cache invalidation.
        state=self.state();p=state['pos']
        if not state.get('flight') and row['pos']==[math.floor(p[0]),math.floor(p[1])-1,math.floor(p[2])]:return False
        params={'pos':row['pos'],'face':face_from(p,row),'expected_state':row['state'],'seconds':5}
        self.book['pending']={'kind':'mine','world':self.c.world,**params};self.save()
        try:rec=self.c.request('mine_block',**params)
        finally:
            self.book['pending']['request_id']=getattr(self.c,'last',None);self.save()
        if rec.get('phase')!='done' or not verified('mine_block',rec,self.c.world,self.c.last,params):
            if never_dispatched_mining(rec,self.c.last,self.c.world,row['pos']):
                self.book['pending']=None;self.skipped.add(tuple(row['pos']));self.save();return False
            raise LeafStopped('Original excavation unconfirmed; no replay')
        self.book['batch']['mined'].append({'pos':row['pos'],'item':leaf_id(row),'request_id':self.c.last})
        self.book['metrics']['mined']+=1;self.book['pending']=None;self.save();return True
    def batch_gains(self,state):
        batch=self.book['batch'];limits=Counter(r['item'] for r in batch['mined'])+Counter(self.book['outstanding']);actual=leaf_counts(state);gains={}
        for item in set(actual)|set(batch['before']):
            n=actual.get(item,0)-batch['before'].get(item,0)
            if n<0 or n>limits[item]:raise LeafStopped('Batch leaf quantity exceeds confirmed mining receipts')
            if n:gains[item]=n
        return gains,limits
    def settle_batch(self):
        batch=self.book['batch']
        if batch is None or self.book['pending']:raise LeafStopped('Batch cannot settle past an unknown request')
        # Allow packet ordering to settle once per batch, never twelve seconds per leaf.
        deadline=self.clock()+self.config.get('pickup_grace_seconds',.5)
        while True:
            s=self.state();gains,limits=self.batch_gains(s)
            if sum(gains.values())==sum(limits.values()) or self.clock()>=deadline:break
            self.sleep(.05)
        prior=set(batch['prior_drop_ids']);attempted=set(batch.get('attempted_drop_ids',[]))
        for _ in range(len(batch['mined'])):
            s=self.state();gains,limits=self.batch_gains(s)
            drops=[e for e in s.get('entities',[]) if e.get('type')=='minecraft:item'
                   and isinstance(e.get('uuid'),str) and e['uuid'] not in prior|attempted
                   and point(e.get('pos')) and type(e.get('stack',{}).get('count')) is int
                   and 0<e['stack']['count']<=limits[e['stack'].get('item')]-gains.get(e['stack'].get('item'),0)
                   and any(r['item']==e['stack'].get('item') and math.dist(e['pos'],[v+.5 for v in r['pos']])<=16 for r in batch['mined'])]
            if not drops:break
            drop=min(drops,key=lambda e:math.dist(e['pos'],s['pos']));attempted.add(drop['uuid'])
            batch['attempted_drop_ids']=sorted(attempted)
            self.book['pending']={'kind':'batch_pickup','drop':drop,'before':leaf_counts(s),'world':self.c.world};self.save()
            try:picked=self.pickup(self.c,drop,s)
            finally:
                self.book['pending']['request_id']=getattr(self.c,'last',None);self.save()
            if not picked:
                event=getattr(self.c,'last_terminal_evidence',{}) or {};current=self.state()
                known=(not getattr(self.c,'native_inflight',None) and not getattr(self.c,'unconfirmed_native_request',None)
                       and event.get('request_id')==getattr(self.c,'last',None)
                       and event.get('task_session')==getattr(self.c,'task',None)
                       and event.get('revision_after')==current.get('control_revision')
                       and pickup_refusal(event,drop,self.c.world))
                if not known:raise LeafStopped('Exact batch drop pickup unresolved; original UUID retained')
                self.batch_gains(current)
                self.book.setdefault('retained_pickup_receipts',[]).append(event)
                self.book['pending']=None;self.save();continue
            after=self.state();delta={i:leaf_counts(after).get(i,0)-leaf_counts(s).get(i,0) for i in set(leaf_counts(after))|set(leaf_counts(s))}
            # Moving to one pile can absorb another pile from the same confirmed
            # batch. Accept that only within the remaining mined-item budget.
            self.batch_gains(after)
            if delta.get(drop['stack']['item'],0)<drop['stack']['count'] or any(n<0 for n in delta.values()):raise LeafStopped('Pickup inventory differs from confirmed leaf budget')
            if any(e.get('uuid')==drop['uuid'] for e in after.get('entities',[])):raise LeafStopped('Picked drop still visible; observe original outcome')
            self.book['pending']=None;self.save()
        s=self.state();gains,limits=self.batch_gains(s);missing={i:n-gains.get(i,0) for i,n in limits.items() if n>gains.get(i,0)}
        if missing:
            self.book.setdefault('uncollected',[]).append({'mined':batch['mined'],'missing':missing,'time':s.get('time'),'reason':'not credited; no matching pickup observed'})
        self.book['outstanding']=missing
        self.credit(gains,s);self.book['batch']=None;self.book['metrics']['batches']+=1;self.save()
        if hasattr(self.c,'set_progress'):self.c.set_progress(done=self.progress(),phase='连续剪叶 · 批次拾取')
        return sum(gains.values())
    def harvest_batch(self,rows):
        self.begin_batch(self.state())
        if self.config.get('execution')=='native_burst':
            from .leaf_native_burst import execute
            self.ensure_shears()
            rows=rows[:max(0,self.config['target']-self.progress())]
            if any(not self.allowed(row) for row in rows):raise LeafStopped('Leaf outside authorized source')
            def record(request):
                self.book['pending']={'kind':'native_burst','request':request};self.save()
            receipt=execute(self.c,rows,self.out/'native-bursts',self.state,record)
            self.book['batch']['mined']=[{'pos':r['pos'],'item':r['item'],'request_id':receipt['id']}for r in receipt['removed']]
            self.book['metrics']['mined']+=len(receipt['removed']);self.book['pending']=None
            by_pos={tuple(r['pos']):r for r in rows}
            self.native_remaining=[by_pos[tuple(r['pos'])] for r in receipt['remaining']]
            self.save();return self.settle_batch()
        for row in rows:
            if self.progress()+len(self.book['batch']['mined'])>=self.config['target']:break
            if not self.allowed(row):raise LeafStopped('Leaf outside authorized source')
            self.mine(row)
        return self.settle_batch()
    def harvest(self,row):return self.harvest_batch([row])>0
    def approach(self,row):
        # Only far stations need access planning. Refresh the target after leaf
        # decay/property changes instead of aborting the entire harvest.
        s=self.state();first=face_from(s['pos'],row)
        for face in dict.fromkeys((first,'up')):
            fresh=self.fresh_leaf(row['pos'])
            if fresh is None:return False
            rec=self.c.request('approach_block',pos=fresh['pos'],face=face,expected_state=fresh['state'],
                               seconds=self.config.get('approach_seconds',12),stand_distance=1.5)
            self.book['metrics']['approaches']+=1
            if rec.get('phase')=='done':return True
            known=APPROACH_REFUSALS|{'Work block state changed','Work block state changed during approach'}
            if rec.get('phase') not in ('error','waiting') or rec.get('detail') not in known:raise LeafStopped('Work approach unresolved: '+str(rec.get('detail')))
        return False
    def store(self):
        s=self.state();self.late_gains(s);keeps={i:min(n,self.book['initial_bag'].get(i,0)) for i,n in leaf_counts(s).items()}
        movable={i:n-keeps[i] for i,n in leaf_counts(s).items() if n>keeps[i]}
        if not movable or not self.config.get('depots'):raise LeafStopped('Leaf depot required; equipment retained')
        if any(n>self.book['gathered'].get(i,0)-self.book['stored'].get(i,0) for i,n in movable.items()):raise LeafStopped('Unaccounted leaf inventory')
        self.book['pending']={'kind':'deposit','before':leaf_counts(s),'keep':keeps};self.save()
        result=self.deposit(self.c,self.config['depots'],keeps);after=self.state();actual=leaf_counts(after)
        if not isinstance(result,dict) or result.get('complete') is not True:raise LeafStopped('Depot transfer incomplete; reconcile original transfer')
        for item,n in movable.items():
            if actual.get(item,0)!=keeps[item]:raise LeafStopped('Deposit quantity mismatch')
            self.book['stored'][item]=self.book['stored'].get(item,0)+n
        self.book['expected_bag']=actual;self.book['pending']=None;self.save()
    def run(self):
        if self.book['batch']:self.settle_batch()  # explicit --resume-batch never replays excavation
        while self.progress()<self.config['target']:
            candidates={}
            for region in self.config['regions']:
                for row in self.scan(region['min'],region['max']):
                    if self.allowed(row) and tuple(row['pos']) not in self.skipped:candidates[tuple(row['pos'])]=row
            mined_before=self.book['metrics']['mined']
            while candidates and self.progress()<self.config['target']:
                s=self.state();self.late_gains(s)
                ordered=sorted(candidates.values(),key=lambda r:math.dist(center(r),s['pos']))
                near=[r for r in ordered if reach_distance(s['pos'],r)<=4]
                if not near:
                    row=ordered[0]
                    if not self.approach(row) or reach_distance(self.state()['pos'],row)>4:
                        candidates.pop(tuple(row['pos']));self.skipped.add(tuple(row['pos']))
                    continue
                item=leaf_id(near[0]);room=capacity(s,item,self.config.get('reserve_slots',2))
                if room<=0:self.store();continue
                limit=min(self.config.get('batch_size',12),room,self.config['target']-self.progress())
                batch=[r for r in near if leaf_id(r)==item][:limit]
                for row in batch:candidates.pop(tuple(row['pos']))
                self.harvest_batch(batch)
                for row in self.native_remaining:
                    key=tuple(row['pos']);self.native_retries[key]+=1
                    if self.native_retries[key]<2:candidates[key]=row
                    else:self.skipped.add(key)
                self.native_remaining=[]
            if self.book['metrics']['mined']==mined_before:raise LeafStopped('Authorized sources exhausted or inaccessible')
        s=self.state();self.late_gains(s)
        for item in set(self.book['initial_bag'])|set(self.book['gathered'])|set(self.book['stored']):
            expected=self.book['initial_bag'].get(item,0)+self.book['gathered'].get(item,0)-self.book['stored'].get(item,0)
            if leaf_counts(s).get(item,0)!=expected:raise LeafStopped('Final retained stock does not match receipts')
        self.book['phase']='complete';self.save();return self.book


def release_or_observe(c):
    """Release a settled native owner even when application pickup is pending.

    An uncertain native request still holds the original heartbeat. Closing a
    live lease before releasing it can invoke the host's logout fallback.
    """
    from native_outcome_fence import wait_exact_idle_terminal
    while True:
        state=c.raw();lease=state.get('supervision_lease') or {}
        if not state.get('connected') or state.get('world_session')!=c.world or state.get('manual_movement') or lease.get('job_session')!=c.task:return
        if getattr(c,'native_leaf_pending',None):c.heartbeat.touch();time.sleep(.25);continue
        try:
            wait_exact_idle_terminal(c,seconds=.5)
            c.checked('material_job_pause',release=True)
            return
        except Exception:
            # This is observation of the same unresolved request, not a retry.
            if getattr(c,'unconfirmed_native_request',None) or getattr(c,'native_inflight',None):
                c.heartbeat.touch();time.sleep(.25);continue
            # A known rejection or changed lease must not cause another pause.
            while True:
                state=c.raw();lease=state.get('supervision_lease') or {}
                if not state.get('connected') or state.get('world_session')!=c.world or state.get('manual_movement') or lease.get('job_session')!=c.task:return
                c.heartbeat.touch();time.sleep(.25)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path('/Applications/.minecraft/versions/26.2/config/twob2tkit/automation'))
    parser.add_argument('--config',type=Path);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--status',action='store_true');parser.add_argument('--run',action='store_true')
    parser.add_argument('--resume-batch',action='store_true',help='Settle only an exactly terminal previous pickup before mining')
    parser.add_argument('--wait-idle-seconds',type=int,default=0,help='Observe manual input for up to 60 seconds before acquiring control')
    args=parser.parse_args()
    if args.status:print((args.out/'leaf-progress.json').read_text());return
    if args.config is None:parser.error('--config is required unless --status is used')
    config=validate(json.loads(args.config.read_text()))
    if not args.run:print(json.dumps({'valid':True,'target':config['target'],'live_actions':0}));return
    if not 0<=args.wait_idle_seconds<=60:parser.error('Idle wait must be 0..60 seconds')
    if args.wait_idle_seconds:
        from live_snapshot import read_fresh
        end=time.monotonic()+args.wait_idle_seconds;quiet=None;anchor=None
        while True:
            s=read_fresh(args.root);now=time.monotonic();p=s.get('pos')
            ready=(s.get('connected') and not s.get('screen') and not s.get('manual_movement')
                   and s.get('health',0)>=19 and not s.get('safety_hold',{}).get('active')
                   and not s.get('supervision_lease') and point(p))
            if not ready or anchor is not None and math.dist(p,anchor)>.2:quiet=None;anchor=None
            if ready:
                if quiet is None:quiet=now;anchor=p
                if now-quiet>=3:break
            if now>=end:raise LeafStopped('Manual input is still active; no controller acquired')
            time.sleep(.2)
    import fcntl
    lock=open(args.root/'leaf-job.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    from live_snapshot import read_fresh
    from material_jobs.protocol import server_key
    state=read_fresh(args.root)
    if not state.get('connected') or server_key(state.get('server'))!=server_key(config['server']) or state.get('dimension')!=config['dimension']:raise LeafStopped('Actual server differs')
    journal=args.out/'leaf-progress.json';resume_receipt=None
    if journal.exists():
        saved=json.loads(journal.read_text())
        if saved.get('world')!=state.get('world_session'):raise LeafStopped('World changed; original batch retained')
        if saved.get('pending') or saved.get('batch'):
            if not args.resume_batch:raise LeafStopped('Resume requires batch reconciliation; no client acquired')
            resume_receipt=retained_batch_refusal(args.out,saved)
        elif saved.get('expected_bag')!=leaf_counts(state):raise LeafStopped('Inventory differs; no client acquired')
    from material_depots import exchange
    c=RetainedUnknownMaterialClient(args.root,args.out/'control',config['server'],record_experience=False,remote_finish='guard',park_target=config['park_target'],dimension=config['dimension'])
    job=None
    try:
        c.checked('guard',pve_only=True)
        if config.get('execution')=='native_burst':
            from .runtime_update import ensure
            ensure(c,args.root,args.out,config.get('runtime_update'))
            current=c.status()
            if tuple(int(x) for x in current['runtime_version'].split('.'))<(1,8,61):raise LeafStopped('Native leaf burst requires engine 1.8.61 or newer')
            from survival_recovery import ensure_work_food
            ensure_work_food(c,args.out/'food',minimum=20)
        job=LeafHarvester(c,config,args.out,pickup=collect_leaf_drop,deposit=lambda c,p,k:exchange(c,p,deposit=k),resume_batch=args.resume_batch,resume_receipt=resume_receipt)
        c.start_progress('自动采集树叶',config['target'],job.progress(),phase='连续剪叶')
        print(json.dumps({'phase':'running','execution':job.book['execution'],'done':job.progress(),'target':config['target']},ensure_ascii=False),flush=True)
        result=job.run();print(json.dumps(result,ensure_ascii=False),flush=True)
    except Exception as error:
        if job is not None:
            job.book.update(phase='waiting',detail=str(error));job.save()
            print(json.dumps({'phase':'waiting','detail':str(error),'pending':job.book['pending'],'batch':job.book['batch']},ensure_ascii=False),flush=True)
        else:raise
    finally:
        try:release_or_observe(c)
        finally:
            if c.heartbeat:c.heartbeat.close()
            if c.foreground_token:c.foreground_token.close()


if __name__=='__main__':main()
