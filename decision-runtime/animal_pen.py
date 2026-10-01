"""One ordinary pen item placement, with durable intent and actual stock/block proof."""
import json
from pathlib import Path
from potato_farm import FarmWait, valid_entity_scope
from potato_harvest import _counts, _lease

ALLOWED = {'minecraft:oak_fence','minecraft:oak_fence_gate','minecraft:torch'}
PRE_DISPATCH_ERROR = 'Target interaction face is occluded or out of reach'
SEEDS = 'minecraft:wheat_seeds'

def _block_structure(row):
    # Light layers and spawn-light hints are observations, not block identity.
    return None if row is None else {k:row.get(k) for k in ('pos','state','solid','replaceable','passable','fluid','block_entity')}

def _cell_scan(c,cell,checkpoint,hurt):
    checkpoint();before=c.status();_lease(c,before,hurt)
    r=c.request('scan',min=[cell[0]-1,cell[1]-1,cell[2]-1],max=[cell[0]+1,cell[1]+2,cell[2]+1],details=True)
    _lease(c,r,hurt);_counts(r)
    if r['time']<=before['time'] or not valid_entity_scope(r.get('scan_entity_scope')) or not isinstance(r.get('scan_entities'),list) or not isinstance(r.get('blocks'),list):
        raise FarmWait('WAIT_SCAN','Detailed later native block/entity frame is required')
    rows={tuple(v['pos']):v for v in r['blocks']}
    if len(rows)!=len(r['blocks']):raise FarmWait('WAIT_SCAN','Duplicate native block rows')
    return r,rows

def verified_placement_counts(book,receipts=()):
    """Advance only through a continuous chain of completed normal item-minus-one proofs."""
    pending=book.get('pending') or {};counts=pending.get('before_counts');previous=pending.get('time_before')
    if not isinstance(counts,dict) or type(previous)is not int:raise FarmWait('WAIT_RECONCILE','Original exact stock/time evidence is missing')
    counts=counts.copy();seen={tuple(book['cell'])}
    for receipt in receipts:
        proof=receipt.get('proof') or {};times=proof.get('observed_times');cell=receipt.get('cell');item=receipt.get('item')
        if (receipt.get('world_session')!=book['world_session'] or receipt.get('complete') is not True
                or receipt.get('pending') is not None or item not in ALLOWED
                or not isinstance(cell,list) or len(cell)!=3 or any(type(v)is not int for v in cell) or tuple(cell) in seen
                or proof.get('before_counts')!=counts or type(proof.get('time_before'))is not int
                or proof['time_before']<=previous or not isinstance(times,list) or len(times)!=2
                or any(type(t)is not int for t in times) or not proof['time_before']<times[0]<times[1]
                or counts.get(item,0)<1):
            raise FarmWait('WAIT_RECONCILE','Later placement receipts are not an exact same-world chronological stock chain')
        expected=counts.copy();expected[item]-=1
        if not expected[item]:del expected[item]
        if proof.get('after_counts')!=expected:raise FarmWait('WAIT_RECONCILE','Later receipt changed more than its one placed item')
        counts=expected;previous=times[-1];seen.add(tuple(cell))
    return counts

def reconcile_no_dispatch(c,item,cell,out,checkpoint=lambda:None,*,completed_receipts=()):
    """Read-only game reconciliation; retain rejected intent, never fabricate a placement ACK."""
    from kit_runtime.journal import write_json
    path=Path(out)/('place-'+','.join(map(str,cell))+'.json');book=json.loads(path.read_text());pending=book.get('pending') or {}
    receipt=pending.get('receipt') or {}
    if (book.get('world_session')!=c.world or book.get('item')!=item or book.get('cell')!=cell
            or pending.get('operation')!='place' or receipt.get('phase')!='error'
            or receipt.get('detail')!=PRE_DISPATCH_ERROR or not isinstance(receipt.get('id'),str) or not receipt['id']):
        raise FarmWait('WAIT_RECONCILE','Only this exact known synchronous pre-dispatch rejection may be reconciled')
    expected=verified_placement_counts(book,completed_receipts)
    checkpoint();hurt=c.status()['recent_hurt_at'];times=[]
    for _ in range(2):
        state,rows=_cell_scan(c,cell,checkpoint,hurt)
        if (_counts(state)!=expected or _block_structure(rows.get(tuple(cell)))!=_block_structure(pending.get('target_before'))
                or rows.get(tuple(pending['support']),{}).get('state')!=pending['support_state']
                or state['time']<=pending['time_before'] or times and state['time']<=times[-1]):
            raise FarmWait('WAIT_RECONCILE','Fresh target/support or whole stock differs from the known rejected intent and verified later actions')
        times.append(state['time'])
    book.setdefault('rejected_intents',[]).append({'original_pending':pending,'observed_times':times,
        'verified_later_receipts':list(completed_receipts),'expected_current_counts':expected,
        'classification':'known_synchronous_pre_dispatch_rejection','placement_ack':False,'server_verified':False})
    book['pending']=None;write_json(path,book);return book

def block_id(row):
    return row.get('state','').split('}',1)[0].removeprefix('Block{')

def entity_clear(entities,cell):
    for e in entities:
        p=e.get('pos');kind=e.get('type');baby=e.get('is_baby') is True
        if not isinstance(p,list) or len(p)!=3:raise FarmWait('WAIT_ENTITY','Actual entity position is missing')
        w,h=(.225,.7) if kind=='minecraft:cow' and baby else (.45,1.4) if kind=='minecraft:cow' else (1,3)
        if p[0]+w>cell[0] and p[0]-w<cell[0]+1 and p[2]+w>cell[2] and p[2]-w<cell[2]+1 and p[1]+h>cell[1] and p[1]<cell[1]+1.5:
            return False
    return True

def place(c,item,cell,out,checkpoint=lambda:None,*,axis=None):
    """Caller approaches safely first; no movement or repeated use is created here."""
    from kit_runtime.journal import write_json
    if item not in ALLOWED or not isinstance(cell,list) or len(cell)!=3 or any(type(v)is not int for v in cell):
        raise ValueError('One approved pen item and integer target cell are required')
    directory=Path(out);directory.mkdir(parents=True,exist_ok=True);path=directory/('place-'+','.join(map(str,cell))+'.json')
    book=json.loads(path.read_text()) if path.exists() else {'world_session':c.world,'item':item,'cell':cell,'pending':None}
    def save():write_json(path,book)
    if book['world_session']!=c.world or book['item']!=item or book['cell']!=cell:raise FarmWait('WAIT_CONTROL','Saved placement belongs to another scope')
    if book.get('pending'):raise FarmWait('WAIT_RECONCILE','Saved placement intent is unresolved; no repeated use')
    checkpoint();state=c.status();hurt=state['recent_hurt_at']
    def scan():
        return _cell_scan(c,cell,checkpoint,hurt)
    state,rows=scan()
    if book.get('complete'):
        if block_id(rows.get(tuple(cell),{}))!=item:raise FarmWait('WAIT_RECONCILE','Previously placed item is no longer observed')
        return {**book,'prior_receipt_reuse':True}
    source=max((r for r in state['inventory'] if r['slot']<36 and r['item']==item and r['count']>0),key=lambda r:r['count'],default=None)
    if source is None:raise FarmWait('WAIT_ITEM','Actual carried pen material is unavailable')
    book['pending']={'operation':'select_item','item':item,'slot':source['slot']};save()
    receipt=c.request('select_item',item=item,slot=source['slot']);after=c.status();_lease(c,after,hurt)
    if receipt.get('phase')!='done' or _counts(after)!=_counts(state) or after.get('hand',{}).get('item')!=item:
        raise FarmWait('WAIT_RECONCILE','Material selection outcome is unknown')
    book['pending']=None;save();before,rows=scan();above=rows.get(tuple(cell));support=[cell[0],cell[1]-1,cell[2]];floor=rows.get(tuple(support),{})
    if (floor.get('fluid') is not False or floor.get('block_entity') is not False
            or item!='minecraft:torch' and floor.get('solid') is not True
            or item=='minecraft:torch' and block_id(floor)!='minecraft:oak_fence'
            or above and not (above.get('state')=='Block{minecraft:short_grass}' and above.get('replaceable') is True)):
        raise FarmWait('WAIT_PLACE','Fresh safe support and air/replaceable short-grass post cell are required')
    if not entity_clear(before['scan_entities'],cell):raise FarmWait('WAIT_ENTITY','Actual animal/entity body intersects the new post cell')
    if before.get('hand',{}).get('item')!=item or before['hand'].get('count',0)<1:raise FarmWait('WAIT_HAND','Fresh selected material changed')
    if above:
        if above.get('fluid') is not False or above.get('block_entity') is not False or above.get('passable') is not True:
            raise FarmWait('WAIT_PLACE','Only actual dry replaceable short grass may be cleared')
        pre_ids={e.get('uuid') for e in before.get('entities',[]) if e.get('type')=='minecraft:item'}
        book['pending']={'operation':'clear_grass','cell':cell,'expected_state':above['state'],'support_state':floor['state'],
                         'before_counts':dict(_counts(before)),'hand_before':before['hand'],'pre_drop_ids':sorted(pre_ids),'time_before':before['time']};save();checkpoint()
        receipt=c.request('mine_block',pos=cell,face='up',expected_state=above['state'],seconds=6)
        book['pending']['receipt']={k:receipt.get(k) for k in ('id','phase','detail','time')};save()
        if receipt.get('phase')!='done':raise FarmWait('WAIT_RECONCILE','Single short-grass mining outcome is unknown; do not repeat')
        times=[];maximum=0;owned=[]
        for _ in range(8):
            after,observed=scan();a,b=_counts(before),_counts(after);gain=b[SEEDS]-a[SEEDS]
            nearby={e.get('uuid'):e for e in after.get('entities',[])};drops=[]
            for e in after['scan_entities']:
                if e.get('type')!='minecraft:item':continue
                stack=nearby.get(e.get('uuid'),{}).get('stack',{})
                if (e.get('uuid') in pre_ids or stack.get('item')!=SEEDS or type(stack.get('count'))is not int
                        or stack['count']!=1 or e.get('id')!=nearby.get(e.get('uuid'),{}).get('id')):
                    raise FarmWait('WAIT_RECONCILE','Only a new exact one-seed drop from this grass clear is accepted')
                drops.append({'uuid':e['uuid'],'id':e['id'],'stack':stack,'pos':e['pos']})
            total=gain+sum(d['stack']['count'] for d in drops);maximum=max(maximum,total)
            valid=(tuple(cell) not in observed and observed.get(tuple(support),{}).get('state')==floor['state']
                   and gain>=0 and 0<=total<=1 and total==maximum
                   and all(a[k]==b[k] for k in a.keys()|b.keys() if k!=SEEDS)
                   and after.get('hand')==before['hand'] and after.get('selected_slot')==before.get('selected_slot'))
            if valid:
                if not times or after['time']>times[-1]:times.append(after['time'])
                owned=drops
                if len(times)==2:break
            else:times=[]
        if len(times)!=2:raise FarmWait('WAIT_RECONCILE','Two later AIR/support frames and actual normal seed stock/drop conservation are required')
        book['grass_clear']={**book['pending'],'observed_times':times,'after_counts':dict(_counts(after)),
                             'observed_seed_gain':gain,'observed_seed_drops':owned,'normal_loot_total':total,'server_verified':False}
        book['pending']=None;save();before,rows=scan();above=rows.get(tuple(cell));floor=rows.get(tuple(support),{})
        if above or floor.get('state')!=book['grass_clear']['support_state']:raise FarmWait('WAIT_RECONCILE','Cleared target/support changed before placement')
        if not entity_clear(before['scan_entities'],cell):raise FarmWait('WAIT_ENTITY','Observed seed/entity body remains in the post cell; caller may collect it normally')
    book['pending']={'operation':'place','support':support,'support_state':floor['state'],'target_before':above,
                     'before_counts':dict(_counts(before)),'hand_before':before['hand'],'time_before':before['time']};save();checkpoint()
    receipt=c.request('interact',pos=support,face='up',expected_state=floor['state'],expected_hand=item)
    book['pending']['receipt']={k:receipt.get(k) for k in ('id','phase','detail','time')};save()
    if receipt.get('phase')!='done':raise FarmWait('WAIT_RECONCILE','Single normal placement outcome is unknown')
    times=[]
    for _ in range(8):
        after,observed=scan();placed=observed.get(tuple(cell),{});expected=_counts(before);expected[item]-=1
        if not expected[item]:del expected[item]
        state_text=placed.get('state','');hand=after.get('hand',{});left=before['hand']['count']-1
        valid=(block_id(placed)==item and placed.get('fluid') is False and placed.get('block_entity') is False
               and _counts(after)==expected and hand.get('count')==left
               and hand.get('item')==(item if left else 'minecraft:air') and after['selected_slot']==before['selected_slot'])
        if item=='minecraft:oak_fence':valid=valid and 'waterlogged=false' in state_text
        if item=='minecraft:oak_fence_gate':valid=valid and 'open=false' in state_text and 'powered=false' in state_text
        if item=='minecraft:oak_fence_gate' and axis:valid=valid and any('facing='+v in state_text for v in (('north','south') if axis=='z' else ('east','west')))
        if valid:
            if not times or after['time']>times[-1]:times.append(after['time'])
            if len(times)==2:
                book['proof']={**book['pending'],'after_counts':dict(_counts(after)),'after_state':state_text,'observed_times':times}
                book['pending']=None;book['complete']=True;save();return book
        else:times=[]
    raise FarmWait('WAIT_RECONCILE','Actual item-minus-one and two new placed-state frames were not proved')
