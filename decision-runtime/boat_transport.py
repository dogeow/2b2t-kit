"""Ordinary boat placement and lead use; actual server entities witness each intent."""
from pathlib import Path
import hashlib,json,math,time
from material_plan import inventory_counts
from kit_runtime.journal import write_json
from vehicle_observation import read_frame

def dry_support(row):
    """A village path has a real 15/16 collision floor despite solid=false."""
    return bool(row and not row.get('fluid')and not row.get('block_entity')and
                (row.get('solid')is True or row.get('state')=='Block{minecraft:dirt_path}'))

def owned(c,q):
    lease=q.get('supervision_lease')or{}
    if(q.get('connected')is not True or q.get('world_session')!=c.world or q.get('manual_movement')
            or q.get('health',0)<19 or q.get('food',0)<18 or q.get('screen')
            or q.get('guard_armed')is not True or q.get('guard_pve_only')is not True or q.get('guard_busy')
            or q.get('village_boat_protocol')!=1 or lease.get('kind')!='materials'
            or lease.get('job_session')!=c.task or lease.get('world_session')!=c.world
            or q.get('menu',{}).get('type')!='InventoryMenu'or q.get('menu',{}).get('cursor',{}).get('count')!=0):
        raise RuntimeError('Boat action lost its current healthy idle native owner')
    return q

def vehicles(c,q):
    frame=read_frame(c.root,q)
    if frame is None:raise RuntimeError('Current complete loaded vehicle observation is unavailable; no boat input')
    return frame['vehicles']

def vehicle(c,q,uuid):
    found=next((r for r in vehicles(c,q)if r['uuid']==uuid),None)
    if found is None:raise RuntimeError('Original boat is not currently observed; no substitute')
    return found

def _pointer(c,key,stage):
    q=c.status();server=c.server.strip().lower().removesuffix(':25565')
    world=q.get('world_id','')if server=='singleplayer'else''
    if server=='singleplayer'and not world:raise RuntimeError('Persistent singleplayer world identity required before boat input')
    scope=hashlib.sha256(json.dumps([server,q.get('dimension'),world,key]).encode()).hexdigest()[:24]
    home=Path(c.root)/'village-boats'/scope;home.mkdir(parents=True,exist_ok=True)
    return home/(stage+'-active.json')

def _available(c,key,stage):
    pointer=_pointer(c,key,stage)
    if pointer.exists():
        prior=json.loads(Path(json.loads(pointer.read_text())['journal']).read_text())
        if not prior.get('complete')or prior.get('pending'):raise RuntimeError('Original boat intent is unresolved; no repeated input')
    return pointer

def _journal(c,key,out,stage,before,**extra):
    pointer=_available(c,key,stage)
    out=Path(out);out.mkdir(exist_ok=False);path=out/(stage+'.json')
    book={'world_session':c.world,'before':dict(before),'complete':False,'pending':stage,**extra}
    write_json(path,book);write_json(pointer,{'journal':str(path.resolve())});return path,book

def _one(c,op,path,book,**params):
    previous=c.last
    try:return c.checked(op,**params)
    finally:
        book['request_id']=c.last if c.last!=previous else None;write_json(path,book)

def _wait(c,predicate,*,seconds=8):
    deadline=time.monotonic()+seconds;observed=[]
    while True:
        q=owned(c,c.status());result=predicate(q)
        if result:
            stamp=result.get('observed_at',q['time'])
            if not observed or stamp>observed[-1]:observed.append(stamp)
            if len(observed)>=2:return q,result,observed
        else:observed=[]
        if time.monotonic()>deadline:raise RuntimeError('Original boat input has no conserved two-frame result; retained without replay')
        time.sleep(.15)

def validate_placement_geometry(support,stand,item):
    if(not isinstance(support,list)or not isinstance(stand,list)or len(support)!=3 or len(stand)!=3
            or any(type(v)is not int for v in support+stand)or support[1]!=stand[1]
            or not 1.9<=math.dist(support,stand)<=2.5 or not isinstance(item,str)or not item.endswith('_boat')or 'chest' in item):
        raise ValueError('A normal boat, exact same-level support and separate standing floor are required')

def place(c,support,stand,item,out,checkpoint,allowed_passengers=()):
    validate_placement_geometry(support,stand,item)
    checkpoint();q=owned(c,c.status());_available(c,'support:'+str(support),'place');vehicles(c,q)
    low=[min(support[i],stand[i])-1 for i in range(3)];high=[max(support[i],stand[i])+1 for i in range(3)];high[1]=support[1]+4
    scene=c.checked('scan',min=low,max=high,details=True)
    if scene.get('scan_cells_read')!=scene.get('scan_total_cells'):raise RuntimeError('Complete current boat placement scene required')
    rows={tuple(r['pos']):r for r in scene['blocks']}
    for p in (support,stand):
        floor=rows.get(tuple(p),{})
        if not dry_support(floor):raise RuntimeError('Boat placement requires ordinary dry supporting ground')
    for x in range(support[0]-1,support[0]+2):
        for z in range(support[2]-1,support[2]+2):
            for y in range(support[1]+1,support[1]+4):
                row=rows.get((x,y,z),{})
                if row and(not row.get('passable')or row.get('fluid')or row.get('block_entity')):raise RuntimeError('Boat body space is obstructed')
    c.checked('approach_block',pos=stand,face='up',expected_state=rows[tuple(stand)]['state'],stand_distance=.35,seconds=60)
    c.checked('select_item',item=item);q=owned(c,c.status());before=inventory_counts(q)
    if before[item]<1:raise RuntimeError('No actual carried boat')
    checkpoint();fresh=c.checked('scan',min=low,max=high,details=True)
    current={tuple(r['pos']):r for r in fresh['blocks']}
    if current.get(tuple(support),{}).get('state')!=rows[tuple(support)]['state']:raise RuntimeError('Original support changed before boat use')
    if inventory_counts(fresh)!=before:raise RuntimeError('Boat inventory changed before its original use')
    prior={r['uuid']for r in vehicles(c,fresh)}
    # BoatItem performs its own normal collision/ray checks. The durable intent
    # prevents a different working directory from repeating an unconfirmed use.
    path,book=_journal(c,'support:'+str(support),out,'place',before,support=support,item=item,prior_boats=sorted(prior),allowed_passengers=list(allowed_passengers))
    receipt=_one(c,'interact',path,book,pos=support,face='up',expected_state=rows[tuple(support)]['state'],expected_hand=item)
    expected=before.copy();expected[item]-=1;expected=+expected
    def result(q):
        frame=read_frame(c.root,q)
        if frame is None or inventory_counts(q)!=expected:return None
        born=[r for r in frame['vehicles']if r['uuid']not in prior and r['type']==item
              and math.dist(r['pos'],[support[0]+.5,support[1]+1,support[2]+.5])<=2
              and not r.get('has_custom_name')]
        return {**born[0],'observed_at':frame['time']}if len(born)==1 else None
    q,boat,times=_wait(c,result)
    book.update(complete=True,pending=None,boat=boat,after=dict(inventory_counts(q)),observed_times=times,receipt=receipt,
                passengers_expected={p['uuid']for p in boat['passengers']}<=set(allowed_passengers),
                unexpected_passengers=[p for p in boat['passengers']if p['uuid']not in allowed_passengers],
                proof_scope='new_loaded_server_boat_and_exact_one_boat_debit_in_two_later_frames_not_cargo_readiness')
    write_json(path,book);return book

def attach(c,uuid,out,checkpoint,expected_passengers=()):
    checkpoint();q=owned(c,c.status());_available(c,'boat:'+uuid,'lead');boat=vehicle(c,q,uuid)
    if {p['uuid']for p in boat['passengers']}!=set(expected_passengers):raise RuntimeError('Boat passengers changed before lead use')
    if boat.get('leashed'):
        if boat.get('leash_resolved')is True and boat.get('leash_holder',{}).get('uuid')==q['player_uuid']:
            return {'complete':True,'attached':False,'existing_player_leash_observed':True,'boat':boat,'inventory_credit':0}
        raise RuntimeError('An unresolved or foreign leash is protected')
    c.checked('select_item',item='minecraft:lead');q=owned(c,c.status());boat=vehicle(c,q,uuid);before=inventory_counts(q)
    if before['minecraft:lead']<1 or not boat.get('visible')or boat.get('distance',99)>2.6:raise RuntimeError('One carried lead and the same visible nearby boat are required')
    path,book=_journal(c,'boat:'+uuid,out,'lead',before,uuid=uuid,expected_passengers=list(expected_passengers))
    receipt=_one(c,'interact_entity',path,book,entity_id=boat['id'],expected_uuid=uuid,expected_hand='minecraft:lead')
    expected=before.copy();expected['minecraft:lead']-=1;expected=+expected
    def result(q):
        frame=read_frame(c.root,q)
        if frame is None or inventory_counts(q)!=expected:return None
        row=next((r for r in frame['vehicles']if r['uuid']==uuid),{})
        if(row.get('leashed')is True and row.get('leash_resolved')is True and row.get('leash_holder',{}).get('uuid')==q['player_uuid']
                and {p['uuid']for p in row.get('passengers',[])}==set(expected_passengers)):
            return {**row,'observed_at':frame['time']}
    q,boat,times=_wait(c,result)
    book.update(complete=True,pending=None,boat=boat,after=dict(inventory_counts(q)),observed_times=times,receipt=receipt,
                proof_scope='same_loaded_boat_resolved_player_leash_and_exact_one_lead_debit_in_two_later_frames')
    write_json(path,book);return book
