"""Four bounded farm stages sharing the caller's live MaterialClient/Backend.

No controller, model, UI, reconnection or safety unlock is created here. Unknown
intents remain in the fixed cycle directory and can never be silently replayed.
"""
from collections import Counter
from copy import deepcopy
import itertools
import json
import math
from pathlib import Path
import time

from animal_breed import entity_rows, run as breed_pair
from kit_runtime.journal import write_json
from material_jobs.protocol import JobPaused
from material_depots import exchange
from material_jobs.acquisition import _travel as travel
from material_jobs_backend import _entry_height
from potato_farm import FarmWait, plan as field_plan, _properties
from potato_harvest import POTATO, _counts, _lease, run as harvest_batch
from potato_loot_flight import make_pickup
from drop_collection import collect_drop

DEFAULT_FIELD = {'authorized':True,'center':[761021,63,797869],'radius':2}
SPECIES = ('minecraft:cow','minecraft:sheep')
COOKED = ('minecraft:cooked_beef','minecraft:cooked_mutton','minecraft:baked_potato',
          'minecraft:cooked_porkchop','minecraft:cooked_chicken','minecraft:cooked_rabbit',
          'minecraft:cooked_cod','minecraft:cooked_salmon')
MEAT = {'minecraft:cow':'minecraft:beef','minecraft:sheep':'minecraft:mutton'}


def food_keep(counts,reserve=8):
    """Exchange values are carried keep quantities; reserve eight foods in total."""
    if type(reserve)is not int or reserve<8:raise ValueError('Cooked food reserve must be >=8')
    keep={};left=reserve
    for item in COOKED:
        keep[item]=min(counts.get(item,0),left);left-=keep[item]
    return keep,left


class _Stages:
    def __init__(self,c,b):
        if getattr(b,'client',None) is not c:raise ValueError('Backend must already own this exact injected client')
        self.c,self.b=c,b

    def execute(self,name,profile,cycle,out,checkpoint):
        self.profile,self.cycle,self.checkpoint=profile,cycle,checkpoint
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True);self.path=self.out/'stage.json'
        self.book=json.loads(self.path.read_text()) if self.path.exists() else {
            'world_session':self.c.world,'cycle_id':cycle['id'],'stage':name,'receipts':[],'pending':None}
        def response(phase,code=None,detail=''):
            return {'phase':phase,'code':code,'detail':detail,'receipts':self.book['receipts'],
                    'pending':bool(self.book.get('pending')),'journal':str(self.path)}
        self.response=response
        self.save()
        if self.book.get('world_session')!=self.c.world or cycle.get('world_session')!=self.c.world or self.book.get('cycle_id')!=cycle['id']:
            return response('waiting','WAIT_WORLD','Fresh cycle world/context is required; no old action is adopted')
        if self.book.get('pending'):return response('waiting','WAIT_RECONCILE','Saved intent is unresolved; no stage action replay')
        try:
            self.keep=profile.get('adult_keep',20)
            if type(self.keep)is not int or not 2<=self.keep<=64 or profile.get('potato_reserve',4)!=4:
                raise ValueError('Adult keep must be2..64 and potato reserve exactly4')
            food_keep({},profile.get('cooked_food_reserve',8));self.safe()
            if self.book.get('complete'):return response(self.book['phase'])
            result=getattr(self,name)()
            if result['phase'] in ('done','idle'):
                if self.book.get('pending'):raise FarmWait('WAIT_RECONCILE','Completion still has an unresolved action')
                self.book.update(complete=True,phase=result['phase']);self.save()
            return result
        except JobPaused:
            raise
        except Exception as error:
            self.book['last_wait']={'code':getattr(error,'code','WAIT_RECONCILE' if self.book.get('pending') else 'WAIT_STAGE'),'detail':str(error)};self.save()
            return response('waiting',self.book['last_wait']['code'],str(error))

    def save(self):write_json(self.path,self.book)
    def safe(self):
        self.checkpoint();s=self.c.status();hurt=self.book.setdefault('recent_hurt_at',s.get('recent_hurt_at'))
        _lease(self.c,s,hurt);_counts(s);return s
    def observe(self,region):
        before=self.safe();r=self.c.request('scan',min=region['min'],max=region['max'],details=True)
        _lease(self.c,r,self.book['recent_hurt_at']);_counts(r)
        if r['time']<=before['time']:raise FarmWait('WAIT_SCAN','A later detailed native observation is required')
        rows=entity_rows(r,{'species':'minecraft:cow'})
        if any(e.get('type') in SPECIES and type(e.get('is_baby'))is not bool for e in rows.values()):
            raise FarmWait('WAIT_SCAN','Actual adult/baby metadata is unavailable')
        return r,rows
    def start(self,kind,**params):
        s=self.safe();self.book['pending']={'operation':kind,'before_time':s['time'],'params':params,
            'before_counts':dict(_counts(s)), 'before_revision':s.get('control_revision'),
            'before_inventory':deepcopy(s['inventory']), 'before_cursor':deepcopy(s.get('menu',{}).get('cursor'))};self.save()
    def finish_action(self,receipt):
        self.book['receipts'].append(receipt);self.book['pending']=None;self.save()
    def move(self,target):
        if math.dist(self.safe()['pos'],target)<=.45:return
        self.start('travel',target=target);trace=[]
        self.b.prepare_travel();travel(self.c,target,self.checkpoint,trace)
        if math.dist(self.safe()['pos'],target)>.65:raise FarmWait('WAIT_POSITION','Native arrival is unproved')
        self.finish_action({'kind':'travel','target':target,'trace':trace})
    def depots(self):
        positions=self.profile.get('depots',self.b.profile.get('depots',[]));approved=self.b.profile.get('depots',[])
        if not positions or any(p not in approved for p in positions):
            raise FarmWait('WAIT_DEPOTS','Only current approved depots may be used')
        return positions
    def store(self,keep):
        positions=self.depots();before=_counts(self.safe());self.start('depot_exchange',keep=keep)
        self.b.prepare_travel();self.b.stage_near_base(positions)
        receipt=exchange(self.c,positions,deposit=keep)
        if not receipt.get('complete'):raise FarmWait('WAIT_DEPOT','Deposit did not return a complete verified receipt')
        actual=_counts(self.safe())
        if any(actual[item]!=min(before[item],quantity) for item,quantity in keep.items()):
            raise FarmWait('WAIT_RECONCILE','Deposit receipt lacks actual carried keep quantities')
        self.finish_action({'kind':'depot_exchange','keep':keep,'receipt':receipt})
    def fetch(self,targets):
        self.depots();self.start('fetch',targets=targets);r=self.b.fetch(targets)
        if r.get('phase')!='done':raise FarmWait('WAIT_SUPPLY','Supply action is not a completed receipt')
        stock=_counts(self.safe())
        if any(stock[item]<count for item,count in targets.items()):
            raise FarmWait('WAIT_RECONCILE','Supply receipt lacks actual carried target quantities')
        self.finish_action({'kind':'fetch','receipt':r})
    def harvest_store(self):
        harvested=0
        for number,request in enumerate(self.profile.get('potato_fields',[DEFAULT_FIELD])):
            layout=field_plan(request);region={'min':layout['scan_min'],'max':layout['scan_max']}
            scan,_=self.observe(region);rows={tuple(r['pos']):r for r in scan['blocks']}
            mature=[p for p in layout['cells'] if _properties(rows.get((p[0],p[1]+1,p[2]),{}),'potatoes','age',7)==7][:4]
            if not mature:continue
            if _counts(scan)[POTATO]<5:
                self.fetch({POTATO:5})
                if _counts(self.safe())[POTATO]<5:
                    return self.response('waiting','WAIT_SEED_RESERVE','Approved stock did not supply four retained seeds plus one reseed; no crop broken')
            center=layout['center'];self.move([center[0]+.5,center[1]+1.6,center[2]+.5])
            self.start('harvest',field=request,cells=mature)
            r=harvest_batch(self.c,{**request,'cells':mature,'bonemeal':False},self.out/('field-'+str(number)),
                            self.checkpoint,max_cells=4,bonemeal_budget=0,pickup=make_pickup(center,checkpoint=self.checkpoint))
            self.checkpoint()
            inner=json.loads(Path(r['journal']).read_text())
            if inner.get('pending'):
                self.book['pending']['inner_journal']=r['journal'];self.save();return self.response('waiting',r.get('code'),'Harvest/pickup/reseed remains unresolved')
            self.finish_action({'kind':'harvest','result':r})
            if r.get('phase')!='done':return self.response('waiting',r.get('code'),r.get('detail',''))
            harvested+=r['harvested_replanted']
        stock=_counts(self.safe())
        if stock[POTATO]>4:self.store({POTATO:4})
        return self.response('done' if harvested or self.book['receipts'] else 'idle')
    def livestock(self):
        region=self.profile.get('livestock_region')
        if not region:raise FarmWait('WAIT_REGION','Explicit bounded livestock region is required')
        r,rows=self.observe(region)
        if any(e.get('type') in SPECIES and type(e.get('has_custom_name')) is not bool for e in rows.values()):
            raise FarmWait('WAIT_METADATA','Actual named-animal metadata is required; no livestock action')
        adults={kind:[e for e in rows.values() if e.get('type')==kind and e.get('alive') is True
                     and e.get('is_baby') is False and e.get('has_custom_name') is False
                     and self.inside(e['pos'],region)]
                for kind in self.profile.get('livestock_types',SPECIES)}
        if any(kind not in SPECIES for kind in adults):raise ValueError('Caretaker livestock is cow/sheep only')
        return region,r,rows,adults
    @staticmethod
    def inside(pos,region):
        return all(low<=value<high+1 for low,value,high in zip(region['min'],pos,region['max']))
    @staticmethod
    def isolated(animal,rows):
        return not any(e['uuid']!=animal['uuid'] and e.get('alive') is True and 'is_baby' in e
                       and abs(e['pos'][0]-animal['pos'][0])<1.9 and abs(e['pos'][2]-animal['pos'][2])<1.9
                       and abs(e['pos'][1]-animal['pos'][1])<2 for e in rows.values())
    def attack_position(self,animal,state,region):
        if state.get('on_ground') is False and self.near_pair([animal],state):return animal
        cells={tuple(row['pos']):row for row in state['blocks']};x,z=map(math.floor,(animal['pos'][0],animal['pos'][2]))
        stands=[]
        for a in range(x-2,x+3):
            for b in range(z-2,z+3):
                y=_entry_height(cells,a,b,math.floor(animal['pos'][1]))
                p=[a+.5,y+.5,b+.5] if y is not None else None
                if p and self.inside(p,region) and 1<=math.dist(p,animal['pos'])<=2.4:
                    # An airborne body also needs the third block clear; no ceiling or entity is pushed aside.
                    if ((a,y+2,b) not in cells and all(e['uuid']==animal['uuid'] or e.get('alive') is not True
                            or 'is_baby' not in e or math.dist(p,e['pos'])>=1 for e in state['scan_entities'])):stands.append(p)
        if not stands:raise FarmWait('WAIT_ATTACK_POSITION','No observed dry clear airborne normal-reach animal stand')
        self.move(min(stands,key=lambda p:math.dist(p,state['pos'])))
        fresh,rows=self.observe(region);target=rows.get(animal['uuid'],{})
        if (target.get('has_custom_name') is not False or target.get('is_baby') is not False
                or target.get('alive') is not True or fresh.get('on_ground') is not False
                or not self.near_pair([target],fresh) or not self.isolated(target,rows)):
            raise FarmWait('WAIT_ATTACK_POSITION','Fresh actual airborne reach and isolated adult are required after approach')
        return target
    def near_pair(self,pair,state):
        eye=[state['pos'][0],state['pos'][1]+1.62,state['pos'][2]]
        return all(e.get('visible') is True and math.dist(eye,[e['pos'][0],e['pos'][1]+(.77 if e['type']=='minecraft:cow' else .715),e['pos'][2]])<=2.8 for e in pair)
    def breed(self):
        if not self.profile.get('livestock_types',SPECIES if self.profile.get('livestock_region') else ()):return self.response('idle')
        region,state,rows,adults=self.livestock();did=0
        for kind,animals in adults.items():
            if len(animals)<2:continue
            pairs=[p for p in itertools.combinations(animals,2) if math.dist(p[0]['pos'],p[1]['pos'])<=4]
            if not pairs:continue
            pair=min(pairs,key=lambda p:sum(math.dist(e['pos'],state['pos']) for e in p))
            if _counts(self.safe())['minecraft:wheat']<2:self.fetch({'minecraft:wheat':2})
            if not self.near_pair(pair,self.safe()):
                cells={tuple(v['pos']):v for v in state['blocks']};x=math.floor(sum(e['pos'][0] for e in pair)/2);z=math.floor(sum(e['pos'][2] for e in pair)/2)
                stands=[]
                for a in range(x-2,x+3):
                    for b in range(z-2,z+3):
                        y=_entry_height(cells,a,b,math.floor(min(e['pos'][1] for e in pair)))
                        p=[a+.5,y,b+.5] if y is not None else None
                        if p and all(1<=math.dist(p,e['pos'])<=2.4 for e in pair):stands.append(p)
                if not stands:return self.response('waiting','WAIT_POSITION','No fresh dry normal-reach animal stand; no feeding')
                self.move(min(stands,key=lambda p:math.dist(p,self.safe()['pos'])))
            state,rows=self.observe(region);pair=[rows.get(e['uuid'],{}) for e in pair]
            if not all(e.get('alive') is True and e.get('is_baby') is False for e in pair) or not self.near_pair(pair,state):
                return self.response('waiting','WAIT_PAIR','Pair moved outside normal reach; no feeding')
            center=[math.floor(state['pos'][0]),math.floor(state['pos'][1]),math.floor(state['pos'][2])]
            self.start('breed',species=kind,adults=[e['uuid'] for e in pair])
            result=breed_pair(self.c,{'authorized':True,'species':kind,'adults':[e['uuid'] for e in pair],'center':center,'radius':4},self.out/kind.split(':')[1],self.checkpoint)
            self.checkpoint()
            inner=json.loads(Path(result['journal']).read_text())
            if inner.get('pending'):
                self.book['pending']['inner_journal']=result['journal'];self.save();return self.response('waiting',result.get('code'),'A food interaction is unresolved')
            self.finish_action({'kind':'breed','species':kind,'result':result});did+=int(result.get('phase')=='done')
            if result.get('phase')!='done':return self.response('waiting',result.get('code'),result.get('detail',''))
        return self.response('done' if did else 'idle')
    def surplus(self):
        if not self.profile.get('livestock_types',SPECIES if self.profile.get('livestock_region') else ()):return self.response('idle')
        did=0
        for _ in range(4):
            region,state,rows,adults=self.livestock()
            excessive=[e for kind,items in adults.items() if len(items)>self.keep for e in items]
            if not excessive:return self.response('done' if did else 'idle')
            if state.get('material_slaughter_protocol',0)<1:return self.response('waiting','WAIT_CAPABILITY','Actual material_slaughter_protocol>=1 is required; no old attack API fallback')
            cooldown=state.get('attack_strength')
            if type(cooldown) not in (int,float) or not math.isfinite(cooldown) or not 0<=cooldown<=1:
                return self.response('waiting','WAIT_CAPABILITY','Actual attack cooldown metadata is required; no attack')
            if any(region['max'][i]-region['min'][i]+1>32 for i in range(3)) or math.prod(region['max'][i]-region['min'][i]+1 for i in range(3))>8192:
                return self.response('waiting','WAIT_SLAUGHTER_REGION','Register a protocol-sized local herd region; no attack')
            animal=next((e for e in sorted(excessive,key=lambda e:math.dist(e['pos'],state['pos'])) if self.isolated(e,rows)),None)
            if animal is None:return self.response('waiting','WAIT_ISOLATED_ADULT','No isolated excess adult; babies/other living entities are protected')
            animal=self.attack_position(animal,state,region)
            result=self.slaughter(animal,region)
            if result['phase']!='done':return result
            did+=1
        _,_,_,adults=self.livestock()
        result=self.response('done');result['remaining_surplus']=sum(max(0,len(v)-self.keep) for v in adults.values())
        return result
    def attack_ready(self,animal,region):
        for _ in range(32):
            region,state,rows,adults=self.livestock();target=rows.get(animal['uuid'],{})
            if (target.get('type')!=animal['type'] or target.get('alive') is not True
                    or target.get('is_baby') is not False or target.get('has_custom_name') is not False
                    or not self.inside(target['pos'],region) or len(adults.get(animal['type'],[]))<=self.keep):
                raise FarmWait('WAIT_TARGET','Fresh exact unnamed excess adult must remain inside the authorized region')
            if state.get('on_ground') is not False or not self.near_pair([target],state) or not self.isolated(target,rows):
                raise FarmWait('WAIT_ATTACK_POSITION','Fresh airborne normal reach and isolated target are required before every attack')
            cooldown=state.get('attack_strength')
            if type(cooldown) not in (int,float) or not math.isfinite(cooldown) or not 0<=cooldown<=1:
                raise FarmWait('WAIT_CAPABILITY','Actual attack cooldown metadata is required; no attack')
            if cooldown>=.95:return state,rows,target
            self.checkpoint();time.sleep(.05)
        raise FarmWait('WAIT_ATTACK_COOLDOWN','Ordinary attack cooldown has not recovered; no attack')
    def slaughter(self,animal,region):
        # Dispatch ledger, damage/death ledger and pickup ledger are distinct.
        state=self.safe();weapon=next((r for r in state['inventory'] if r['slot']<36 and r['count']==1
            and r['item'] in ('minecraft:diamond_sword','minecraft:netherite_sword','minecraft:iron_sword')
            and type(r.get('durability'))is int and r['durability']>32),None)
        if weapon is None:return self.response('waiting','WAIT_WEAPON','No actual carried ordinary sword; no attack')
        if state.get('on_ground') is not False or not self.near_pair([animal],state):
            return self.response('waiting','WAIT_ATTACK_POSITION','Actual airborne normal-reach position is required; no attack')
        self.start('select_weapon',item=weapon['item']);r=self.c.request('select_item',item=weapon['item'],slot=weapon['slot'])
        selected=self.safe()
        if (r.get('phase')!='done' or _counts(selected)!=_counts(state)
                or selected.get('hand',{}).get('item')!=weapon['item'] or selected['hand'].get('count')!=1):
            raise FarmWait('WAIT_RECONCILE','Weapon selection lacks actual held weapon and unchanged inventory')
        self.finish_action({'kind':'select_weapon','receipt':r})
        before,rows=self.observe(region);origin=animal['pos'];initial=_counts(before);previous_ids={e.get('uuid') for e in before.get('entities',[]) if e.get('type')=='minecraft:item'}
        allowed={MEAT[animal['type']], 'minecraft:cooked_beef' if animal['type']=='minecraft:cow' else 'minecraft:cooked_mutton'}
        if animal['type']=='minecraft:cow':allowed.add('minecraft:leather')
        else:allowed.update('minecraft:'+color+'_wool' for color in ('white','orange','magenta','light_blue','yellow','lime','pink','gray','light_gray','cyan','purple','blue','brown','green','red','black'))
        owned={};dead=False
        for _ in range(4):
            observed,rows,target=self.attack_ready(animal,region);nearby={e.get('uuid'):e for e in observed.get('entities',[])}
            health=nearby.get(animal['uuid'],{}).get('health')
            if (target.get('alive') is not True or target.get('is_baby') is not False
                    or type(health) not in (int,float) or not math.isfinite(health) or health<=0):
                return self.response('waiting','WAIT_TARGET','Exact live adult/health must be fresh before each new attack')
            if not owned:origin=target['pos'][:]
            self.start('slaughter_attack',uuid=animal['uuid'],health_before=health)
            receipt=self.c.request('material_slaughter_attack',entity_id=target['id'],expected_uuid=target['uuid'],region_min=region['min'],region_max=region['max'],keep_adults=self.keep)
            request_id=getattr(self.c,'last',None)
            self.book['pending'].update(receipt=receipt,request_id=request_id);self.save();dispatch=receipt.get('slaughter_attack') or {}
            matching=(isinstance(request_id,str) and bool(request_id) and dispatch.get('id')==receipt.get('id')==request_id and dispatch.get('expected_uuid')==target['uuid']
                      and dispatch.get('world_session')==self.c.world and dispatch.get('result_scope')=='normal_attack_dispatch_only')
            if (matching and receipt.get('phase')=='error' and dispatch.get('action_sent') is False
                    and dispatch.get('pre_dispatch_rejected') is True):
                self.finish_action({'kind':'attack_rejected_before_dispatch','dispatch':dispatch,'detail':receipt.get('detail')})
                return self.response('waiting','WAIT_ATTACK_REJECTED',receipt.get('detail','Actual host rejected before dispatch'))
            if receipt.get('phase')!='done' or dispatch.get('action_sent') is not True or not matching:
                raise FarmWait('WAIT_RECONCILE','Only a matching actual dispatch receipt is accepted; no attack retry')
            times=[];after=None
            for _ in range(8):
                after,fresh=self.observe(region);entity=next((e for e in after.get('entities',[]) if e.get('uuid')==animal['uuid']),{})
                for drop in after.get('entities',[]):
                    stack=drop.get('stack') or {}
                    if (drop.get('type')=='minecraft:item' and drop.get('uuid') not in previous_ids and stack.get('item') in allowed
                            and type(stack.get('count'))is int and stack['count']>0 and math.dist(drop['pos'],origin)<=3):owned[drop['uuid']]=drop
                current=fresh.get(animal['uuid']);now=entity.get('health')
                dead=(current is not None and current.get('alive') is False or current is None and bool(owned))
                changed=dead or type(now) in (int,float) and 0<=now<health
                if changed:
                    if not times or after['time']>times[-1]:times.append(after['time'])
                    if len(times)==2:break
                else:times=[]
            if len(times)!=2:raise FarmWait('WAIT_RECONCILE','No two-frame actual damage/death evidence; sent attack remains pending')
            self.finish_action({'kind':'attack_observation','dispatch':dispatch,'health_before':health,'health_after':now,
                                'death_observed':dead,'observed_times':times,'server_verified':False})
            if dead:break
        if not dead:return self.response('waiting','WAIT_ATTACK_BUDGET','Bounded proven hits exhausted; no blind continuation')
        if not owned:return self.response('waiting','WAIT_LOOT','Death observed but no identified new drops yet')
        for uuid,drop in owned.items():
            self.start('slaughter_pickup',uuid=uuid,stack=drop['stack']);ok=collect_drop(self.c,drop,observation=after,seconds=12)
            if not ok:raise FarmWait('WAIT_RECONCILE','Exact owned loot pickup is unresolved; no replay')
            self.finish_action({'kind':'slaughter_pickup','uuid':uuid,'stack':drop['stack']})
        expected_gain=Counter()
        for drop in owned.values():expected_gain[drop['stack']['item']]+=drop['stack']['count']
        times=[]
        for _ in range(4):
            state,rows=self.observe(region);gain={k:_counts(state)[k]-initial[k] for k in allowed if _counts(state)[k]>initial[k]}
            if (all(gain.get(item,0)>=quantity for item,quantity in expected_gain.items())
                    and not any(e.get('uuid') in owned for e in state.get('entities',[]))):
                times.append(state['time'])
                if len(times)==2:
                    self.book['receipts'].append({'kind':'slaughter_collected','target_uuid':animal['uuid'],'actual_gain':gain,'observed_times':times,'server_verified':False});self.save();return self.response('done')
            else:times=[]
        self.book['pending']={'operation':'slaughter_loot_proof','owned_uuids':list(owned)};self.save()
        return self.response('waiting','WAIT_RECONCILE','Owned drops or actual gain is not proved twice')
    def cook_store(self):
        stock=_counts(self.safe());reserve=self.profile.get('cooked_food_reserve',8)
        for source,output in (('minecraft:beef','minecraft:cooked_beef'),('minecraft:mutton','minecraft:cooked_mutton')):
            if stock[source]<=0:continue
            recipe=next((r for r in self.b.catalog.recipes.get(output,[]) if r.id in self.b.catalog.smelting and r.count==1 and source in r.cells[0][1]),None)
            if recipe is None:return self.response('waiting','WAIT_RECIPE','Actual current-JAR ordinary cooking recipe unavailable')
            if not self.b.profile.get('furnace_positions'):return self.response('waiting','WAIT_FURNACE','Approved actual furnace positions required')
            amount=min(16,stock[source]);spec={'recipe_id':recipe.id,'source':source,'output':output}
            before=stock.copy();target=stock[output]+amount
            self.start('smelt',recipe=spec,amount=amount);r=self.b.smelt(spec,target)
            if r.get('phase')=='waiting' and isinstance(r.get('requirements'),dict) and r['requirements']:
                # Existing smelt writes its manifest before any loading. Only a
                # matching empty batch list proves that fuel can be fetched without replaying furnace work.
                path=Path(r.get('journal',''))
                manifest=json.loads(path.read_text()) if path.is_file() else {}
                unchanged=_counts(self.safe())==before
                if (manifest.get('world_session')==self.c.world and manifest.get('kind')=='smelt'
                        and all(manifest.get(k)==v for k,v in {**spec,'target':target}.items())
                        and manifest.get('batches')==[] and unchanged
                        and all(isinstance(k,str) and k.startswith('minecraft:') and type(v)is int and v>0
                                for k,v in r['requirements'].items())):
                    self.finish_action({'kind':'smelt_supply_wait','receipt':r,'no_furnace_loading_observed':True})
                    current=_counts(self.safe());self.fetch({k:current[k]+v for k,v in r['requirements'].items()})
                    self.start('smelt',recipe=spec,amount=amount);r=self.b.smelt(spec,target)
            if r.get('phase')!='done':raise FarmWait('WAIT_SMELT','Cooking/fuel batch is not a verified completed receipt')
            actual=_counts(self.safe())
            if actual[source]!=before[source]-amount or actual[output]!=target:
                raise FarmWait('WAIT_RECONCILE','Cooking receipt lacks actual source consumption and cooked-food gain')
            self.finish_action({'kind':'smelt','receipt':r});stock=_counts(self.safe())
        keep,missing=food_keep(stock,reserve)
        if missing:
            self.fetch({'minecraft:baked_potato':stock['minecraft:baked_potato']+missing});stock=_counts(self.safe());keep,missing=food_keep(stock,reserve)
        if missing:return self.response('waiting','WAIT_FOOD_RESERVE','Eight actual cooked foods must remain carried')
        if stock[POTATO]<4:
            self.fetch({POTATO:4});stock=_counts(self.safe())
        keep[POTATO]=4
        for item in stock:
            if item=='minecraft:leather' or item.endswith('_wool'):keep[item]=0
        if any(stock[item]>quantity for item,quantity in keep.items()):self.store(keep)
        final=_counts(self.safe())
        if sum(final[k] for k in COOKED)<reserve or final[POTATO]<4:
            raise FarmWait('WAIT_RESERVE','Verified final food/seed reserve is below policy')
        return self.response('done' if self.book['receipts'] else 'idle')


def create_stages(client,backend):
    """Return callables(profile,cycle,out,checkpoint) without acquiring any client."""
    adapter=_Stages(client,backend)
    return {name:(lambda profile,cycle,out,checkpoint=lambda:None,_name=name:
                  adapter.execute(_name,profile,cycle,out,checkpoint))
            for name in ('harvest_store','breed','surplus','cook_store')}
