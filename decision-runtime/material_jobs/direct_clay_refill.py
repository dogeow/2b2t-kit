"""Convert carried dirt directly on an owned clay bed; no mud mining round trip."""
import time
from pathlib import Path
from types import SimpleNamespace

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .acquisition import _scan,_safe,block_id
from .local_air_path import move
from .mud_conversion import refill_column
from .mud_water_supply import fill_bottle,BOTTLE_SCOPE
from .protocol import JobBlocked


def refill(c,pos,profile,out,checkpoint,*,water_result=None,owned_dirt_journal=None):
    farm=profile.get('clay_conversion_farm')or{}
    if farm.get('authorized')is not True or pos not in farm.get('positions',[]):
        raise JobBlocked('Direct conversion requires an explicitly registered owned bed')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'direct-clay-refill.json'
    if path.exists():raise JobBlocked('Original direct conversion retained; no replay')
    def state():checkpoint();q=c.status();_safe(q);return q
    def observe():return _scan(c,[pos[0],pos[1]-2,pos[2]],pos,state)
    def counts():return inventory_counts(state())
    observed=observe();resume=False
    if owned_dirt_journal is not None:
        import json
        old=json.loads(Path(owned_dirt_journal).read_text())
        resume=(old.get('world_session')==c.world and old.get('pos')==pos and old.get('pending')is None
            and old.get('complete')is not True and [r.get('kind')for r in old.get('receipts',[])]==['place_dirt']
            and any(r['pos']==pos and block_id(r)=='minecraft:dirt'for r in observed))
        if not resume:raise JobBlocked('Only known completed owned dirt placement may resume conversion')
    original=refill_column([r for r in observed if not(resume and r['pos']==pos)],pos)
    if not original or original['filled']:raise JobBlocked('Direct conversion needs an empty bed with its true tip retained')
    if not resume and not counts()['minecraft:dirt']:raise JobBlocked('No actual carried dirt')
    backend=SimpleNamespace(ensure_client=lambda:c,profile=profile,checkpoint=state)
    result=water_result if water_result is not None else fill_bottle(backend)
    receipt=result.get('native_receipt')or{};proof=receipt.get('bottle_water')or{};water=result.get('derived_water_slot')or{}
    payload=lambda r:{k:v for k,v in r.items()if k!='slot'}
    original_slot=proof.get('water_slot');current_slot=water.get('slot')
    slot_proved=original_slot==current_slot
    if not slot_proved:
        relocated=result.get('slot_relocation_receipt')or{}
        old_rows={r['slot']:r for r in receipt.get('inventory',[])if type(r.get('slot'))is int}
        new_rows={r['slot']:r for r in relocated.get('inventory',[])if type(r.get('slot'))is int}
        swapped=payload(old_rows.get(current_slot,{}))
        if resume and swapped.get('item')=='minecraft:dirt'and type(swapped.get('count'))is int and swapped['count']>1:
            swapped={**swapped,'count':swapped['count']-1}
        slot_proved=(relocated.get('phase')=='done'and relocated.get('world_session')==c.world
            and isinstance(relocated.get('id'),str)and bool(relocated['id'])
            and type(original_slot)is int and type(current_slot)is int
            and payload(old_rows.get(original_slot,{}))==payload(water)
            and payload(new_rows.get(current_slot,{}))==payload(water)
            and payload(new_rows.get(original_slot,{}))==swapped
            and {s for s in old_rows if payload(old_rows[s])!=payload(new_rows.get(s,{}))}=={original_slot,current_slot}
            and old_rows.keys()==new_rows.keys())
    source=(profile.get('mud_bucket_source')or{}).get('pos')
    if (result.get('phase')!='done' or receipt.get('phase')!='done'
            or not isinstance(receipt.get('id'),str)or not receipt['id']
            or proof.get('world_session')!=c.world or proof.get('request_id')!=receipt.get('id')
            or proof.get('operation')!='bottle_fill' or proof.get('pos')!=source
            or proof.get('confirmed')is not True or proof.get('unknown_outcome')is not False
            or proof.get('server_hand_confirmed')is not True or proof.get('server_water_slot_confirmed')is not True
            or proof.get('use_count')!=1 or proof.get('potion')!='minecraft:water'
            or proof.get('source_not_consumed_by_bottle_use')is not True or proof.get('confirmation_scope')!=BOTTLE_SCOPE
            or not slot_proved or water.get('item')!='minecraft:potion'
            or water.get('count')!=1 or type(water.get('slot'))is not int
            or not 0<=water['slot']<36
            or next((r for r in state()['inventory']if r.get('slot')==water['slot']),None)!=water):
        raise JobBlocked('Exact original source-water slot is not currently proved')
    book={'world_session':c.world,'pos':pos,'water_request':receipt['id'],'pending':None,'receipts':[],
          'initial_dirt':counts()['minecraft:dirt'],
          'known_owned_dirt_resumed':resume,'original_dirt_journal':str(owned_dirt_journal)if resume else None,
          'retained_water':{'phase':'done','native_receipt':{k:receipt.get(k)for k in('id','phase','world_session','bottle_water','inventory')},
                            'derived_water_slot':water}}
    write_json(path,book)
    if not resume:
        selecting=state();c.checked('select_item',item='minecraft:dirt');selected=state()
        previous={r['slot']:r for r in selecting['inventory']};current={r['slot']:r for r in selected['inventory']}
        if current.get(water['slot'])!=water:
            moved=[r for s,r in current.items()if payload(r)==payload(water)and payload(previous.get(s,{}))!=payload(water)]
            if (len(moved)!=1 or payload(current.get(water['slot'],{}))!=payload(previous.get(moved[0]['slot'],{}))
                    or {s for s in previous if payload(previous[s])!=payload(current.get(s,{}))}!={water['slot'],moved[0]['slot']}):
                raise JobBlocked('Dirt selection water swap unproved; no dirt use sent')
            water=moved[0]
        book['retained_water']['derived_water_slot']=water;book['water_slot_after_dirt_selection']=water['slot'];write_json(path,book)
    # Keep the complete body above the future block even after Flight settles.
    pose=[pos[0]+.5,pos[1]+2.2,pos[2]+.5]
    move(c,pose,out/'above-owned-bed',foot_offset=.2,max_horizontal=24)
    fresh=refill_column([r for r in observe()if not(resume and r['pos']==pos)],pos)
    if not fresh or fresh['filled']or fresh['support']['state']!=original['support']['state']or fresh['tip']['state']!=original['tip']['state']:
        raise JobBlocked('Owned bed changed before fresh dirt placement')
    def use(kind,target,expected,hand,validate):
        before=counts();book['pending']={'kind':kind,'before':dict(before)};write_json(path,book)
        try:r=c.checked('interact',pos=target,face='up',expected_state=expected,expected_hand=hand)
        finally:book['pending']['request_id']=c.last;write_json(path,book)
        deadline=time.monotonic()+6
        while not validate(before,counts(),observe()):
            if time.monotonic()>=deadline:raise JobBlocked('Direct conversion outcome unconfirmed; no replay')
            time.sleep(.15)
        book['receipts'].append({'kind':kind,'request_id':book['pending']['request_id']});book['pending']=None;write_json(path,book)
    if not resume:
        use('place_dirt',original['support']['pos'],original['support']['state'],'minecraft:dirt',
            lambda a,b,rows:a['minecraft:dirt']-b['minecraft:dirt']==1 and any(r['pos']==pos and block_id(r)in('minecraft:dirt','minecraft:grass_block')for r in rows))
        if any(r['pos']==pos and block_id(r)=='minecraft:grass_block'for r in observe()):
            from .owned_grass_refill import finish
            return finish(c,pos,profile,path,out/'owned-grass-recovery',checkpoint)
    before=state();old=next((r for r in before['inventory']if r.get('slot')==water['slot']),None)
    if old!=water:raise JobBlocked('Proved water slot changed; preserve owned dirt')
    c.checked('select_item',item='minecraft:potion',slot=water['slot'])
    after=state();selected=after.get('selected_slot',(after.get('hand')or{}).get('slot'));rows={r['slot']:r for r in after['inventory']}
    previous={r['slot']:r for r in before['inventory']}
    if (type(selected)is not int or payload(rows.get(selected,{}))!=payload(water)
            or selected!=water['slot']and (payload(rows.get(water['slot'],{}))!=payload(previous.get(selected,{}))
                or {s for s in previous if payload(previous[s])!=payload(rows.get(s,{}))}!={selected,water['slot']})):
        raise JobBlocked('Original water selection swap unproved; preserve owned dirt')
    use('water_to_mud',pos,'Block{minecraft:dirt}','minecraft:potion',
        lambda a,b,rows:a['minecraft:potion']-b['minecraft:potion']==1 and b['minecraft:glass_bottle']-a['minecraft:glass_bottle']==1
            and any(r['pos']==pos and block_id(r)in('minecraft:mud','minecraft:clay')for r in rows))
    final=refill_column(observe(),pos)
    if not final or not final['filled']or final['support']['state']!=original['support']['state']or final['tip']['state']!=original['tip']['state']:
        raise JobBlocked('Direct conversion support/tip conservation unproved')
    book.update(complete=True,dirt_consumed=0 if resume else 1,source_preserved=True,support_preserved=True,tip_preserved=True,mud_mining_sent=False)
    write_json(path,book);return book
