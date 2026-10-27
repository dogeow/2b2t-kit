"""Place a normal painting; reroll only our own observed entity and recovered item."""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from material_plan import inventory_counts
from material_jobs.local_air_path import move
from projection_wood import cell_at
from container_hand import select_container_hand
from drop_collection import collect_drop

FACES={2:('north',[0,0,-1]),3:('south',[0,0,1]),4:('west',[-1,0,0]),5:('east',[1,0,0])}


def ready_weapon(c,checkpoint,timeout=3):
    select_container_hand(c);end=time.monotonic()+timeout
    while True:
        q=checkpoint()
        if q.get('attack_strength',0)>=.95 and not q.get('guard_busy'):return q
        if time.monotonic()>end:raise RuntimeError('Held weapon cooldown unconfirmed; no decoration attack sent')
        time.sleep(.1)


def geometry(expected):
    face,delta=FACES[expected['facing']];cell=[math.floor(v)for v in expected['pos']]
    anchor=[a-b for a,b in zip(cell,delta)];p=expected['pos']
    pose=[p[0]+delta[0]*2.5,p[1]-1.4,p[2]+delta[2]*2.5]
    return anchor,face,pose


def reroll(c,expected,out,checkpoint,*,max_attempts=16):
    if (expected.get('type')!='minecraft:painting'or expected.get('invisible')
            or expected.get('variant')!='minecraft:dennis'or expected.get('width')!=3 or expected.get('height')!=3
            or type(max_attempts)is not int or not 1<=max_attempts<=24):raise ValueError('Finite original ordinary Dennis painting required')
    out=Path(out);out.mkdir(parents=True,exist_ok=False);key=checkpoint()['projection_selection']['key'];anchor,face,pose=geometry(expected)
    row=cell_at(c,anchor)
    if not row.get('solid')or row.get('fluid')or row.get('block_entity'):raise RuntimeError('Visible dry original wall required')
    move(c,pose,out/'ordinary-painting-pose',foot_offset=.1,max_horizontal=24,exact_target=True)
    book={'world_session':c.world,'placement_key':key,'expected':expected,'attempts':[],'pending':None,'complete':False};path=out/'painting.json'
    def save():write_json(path,book)
    def audit():
        checkpoint();a=c.request('projection_audit')['projection_audit']
        if a['placement_key']!=key or not a['loaded_chunks_verified']:raise RuntimeError('Original painting scope changed')
        return a
    def around(a):return[e for e in a.get('decorations',[])if e['type']=='minecraft:painting'and math.dist(e['pos'],expected['pos'])<3]
    save()
    for i in range(max_attempts):
        a=audit();existing=around(a)
        if existing:raise RuntimeError('Existing painting at target; never remove an unowned painting')
        before_ids={e['uuid']for e in a.get('decorations',[])};before=inventory_counts(c.status())['minecraft:painting']
        if before!=1:raise RuntimeError('One recovered painting item required before each normal placement')
        if cell_at(c,anchor)['state']!=row['state']:raise RuntimeError('Painting wall changed')
        c.checked('select_item',item='minecraft:painting');book['pending']={'kind':'one_ordinary_painting_use','attempt':i};save()
        try:r=c.checked('interact',pos=anchor,face=face,expected_state=row['state'],expected_hand='minecraft:painting')
        finally:book['pending']['request_id']=c.last;save()
        write_json(out/('%02d-place-native.json'%i),r);end=time.monotonic()+6;stamps=[];actual=None
        while True:
            a=audit();new=[e for e in around(a)if e['uuid']not in before_ids]
            if len(new)==1 and inventory_counts(c.status())['minecraft:painting']==0:
                actual=new[0]
                if a['observed_at']not in stamps:stamps.append(a['observed_at'])
            else:stamps=[]
            if len(stamps)>=2:break
            if time.monotonic()>end:raise RuntimeError('Original painting placement unconfirmed; no duplicate use')
            time.sleep(.1)
        book['attempts'].append({'attempt':i,'actual':actual,'stock_after_place':0});book['pending']=None;save()
        correct=(actual.get('variant')==expected['variant']and actual.get('facing')==expected['facing']
            and actual.get('width')==3 and actual.get('height')==3 and math.dist(actual['pos'],expected['pos'])<=.15)
        if correct:
            book.update(complete=True,actual=actual);save();print('ORIGINAL_DENNIS_PAINTING_MATCHED',i+1,flush=True);return book
        q=ready_weapon(c,checkpoint);drop_ids={e['uuid']for e in q.get('entities',[])if e['type']=='minecraft:item'}
        live=next((e for e in q.get('entities',[])if e['uuid']==actual['uuid']and e['type']=='minecraft:painting'),None)
        if live is None:
            center=[math.floor(v)for v in actual['pos']]
            scene=c.request('scan',min=[v-3 for v in center],max=[v+3 for v in center],details=True)
            if scene.get('phase')!='done':raise RuntimeError('Current owned painting identity scan unconfirmed')
            live=next((e for e in scene.get('scan_entities',[])if e['uuid']==actual['uuid']and e['type']=='minecraft:painting'),None)
        if live is None or math.dist(live['pos'],actual['pos'])>.125:raise RuntimeError('Owned painting identity changed; no attack sent')
        book['pending']={'kind':'one_attack_on_newly_owned_wrong_painting','uuid':actual['uuid'],'variant':actual['variant']};save()
        try:r=c.checked('attack_decoration',placement_key=key,entity_id=live['id'],expected_uuid=actual['uuid'],expected_type='minecraft:painting',expected_pos=actual['pos'],expected_variant=actual['variant'])
        finally:book['pending']['request_id']=c.last;save()
        write_json(out/('%02d-owned-remove-native.json'%i),r);end=time.monotonic()+8;gone=[]
        while True:
            q=checkpoint();a=audit();exists=any(e['uuid']==actual['uuid']for e in a.get('decorations',[]))
            if not exists and a['observed_at']not in gone:gone.append(a['observed_at'])
            elif exists:gone=[]
            if len(gone)>=2 and inventory_counts(q)['minecraft:painting']==1:break
            drops=[e for e in q.get('entities',[])if e['type']=='minecraft:item'and e['uuid']not in drop_ids and e.get('stack',{}).get('item')=='minecraft:painting'and e['stack']['count']==1 and math.dist(e['pos'],actual['pos'])<5]
            if len(gone)>=2 and len(drops)==1:
                if not collect_drop(c,drops[0],q,seconds=15):raise RuntimeError('Owned painting drop not confirmed recovered')
            if time.monotonic()>end:raise RuntimeError('Owned wrong painting removal or recovery unconfirmed; no second attack or placement')
            time.sleep(.1)
        book['pending']=None;book['attempts'][-1].update(owned_wrong_entity_removed=True,item_recovered=True);save()
        c.set_progress(phase='原图挂画：已正常换画 %d 次'%(i+1));print('OWNED_PAINTING_REROLL_RECOVERED',i+1,actual['variant'],actual.get('width'),actual.get('height'),flush=True)
        if actual.get('width')!=3 or actual.get('height')!=3:raise RuntimeError('Available canvas is larger than the original; item recovered, constrain it before another placement')
    raise RuntimeError('Finite painting variant batch exhausted; all wrong paintings recovered')
