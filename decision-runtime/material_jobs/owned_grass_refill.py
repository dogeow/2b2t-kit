"""Recover only this workflow's proved dirt that naturally grew grass."""
import json
import math
import time
from pathlib import Path

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from .acquisition import _scan,_safe,block_id
from .local_air_path import move
from .mud_conversion import refill_column
from .mud_water_supply import BOTTLE_SCOPE
from .protocol import JobBlocked


def finish(c,pos,profile,original_journal,out,checkpoint):
    old=json.loads(Path(original_journal).read_text());retained=old.get('retained_water')or{}
    water=retained.get('derived_water_slot')or{};native=retained.get('native_receipt')or{};proof=native.get('bottle_water')or{}
    pending=old.get('pending')or{};initial=old.get('initial_dirt',(pending.get('before')or{}).get('minecraft:dirt'))
    farm=profile.get('clay_conversion_farm')or{}
    def state():checkpoint();q=c.status();_safe(q);return q
    def counts():return inventory_counts(state())
    def observe():return _scan(c,[pos[0],pos[1]-2,pos[2]],pos,state)
    rows=observe();top=next((r for r in rows if r['pos']==pos),None)
    base=refill_column([r for r in rows if r['pos']!=pos],pos)
    if (farm.get('authorized')is not True or pos not in farm.get('positions',[])or old.get('world_session')!=c.world
            or old.get('pos')!=pos or not top or block_id(top)!='minecraft:grass_block'or not base
            or type(initial)is not int or counts()['minecraft:dirt']!=initial-1
            or not(pending.get('kind')=='place_dirt'or old.get('receipts')and old['receipts'][-1].get('kind')=='place_dirt')
            or old.get('water_slot_after_dirt_selection')!=water.get('slot')
            or next((r for r in state()['inventory']if r.get('slot')==water.get('slot')),None)!=water
            or native.get('phase')!='done'or native.get('id')!=old.get('water_request')
            or proof.get('world_session')!=c.world or proof.get('request_id')!=native.get('id')
            or proof.get('operation')!='bottle_fill'or proof.get('confirmed')is not True
            or proof.get('unknown_outcome')is not False or proof.get('use_count')!=1
            or proof.get('server_hand_confirmed')is not True or proof.get('server_water_slot_confirmed')is not True
            or proof.get('source_not_consumed_by_bottle_use')is not True
            or proof.get('pos')!=(profile.get('mud_bucket_source')or{}).get('pos')
            or water.get('item')!='minecraft:potion'or water.get('count')!=1
            or proof.get('potion')!='minecraft:water'or proof.get('confirmation_scope')!=BOTTLE_SCOPE):
        raise JobBlocked('Only proved placed grass and its retained exact water slot may be recovered')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'direct-clay-refill.json'
    if path.exists():raise JobBlocked('Original grass recovery retained; no replay')
    book={'world_session':c.world,'pos':pos,'original_grass_journal':str(original_journal),'pending':None,'receipts':[],
          'known_owned_dirt_resumed':False,'water_request':native['id'],'grass_recovered':True}
    def save():write_json(path,book)
    def until(predicate):
        deadline=time.monotonic()+6
        while not predicate():
            if time.monotonic()>=deadline:raise JobBlocked('Owned grass recovery outcome unproved; no replay')
            time.sleep(.15)
    tools=[r for r in state()['inventory']if r.get('slot',99)<36 and r.get('item')in('minecraft:diamond_shovel','minecraft:netherite_shovel')
           and r.get('durability',0)>=33 and not any(e.get('id')=='minecraft:silk_touch'for e in r.get('enchantments',[]))]
    if not tools:raise JobBlocked('Owned grass recovery needs an ordinary durable shovel')
    tool=max(tools,key=lambda r:r['durability']);c.checked('select_item',item=tool['item'],slot=tool['slot'])
    q=state();before=counts()['minecraft:dirt'];old_ids={e['uuid']for e in q.get('entities',[])if e.get('type')=='minecraft:item'}
    book['pending']={'kind':'recover_owned_grass','before_dirt':before};save()
    reply=c.checked('mine_block',pos=pos,face='up',expected_state=top['state'],seconds=20);seq=reply.get('native_sequence')
    book['pending']['request_id']=c.last;save()
    if (reply.get('id')!=c.last or reply.get('world_session')!=c.world or reply.get('mining_target')!=pos or reply.get('server_confirmed')is not True
            or reply.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
            or type(seq)is not int or seq<=0 or reply.get('server_ack_sequence')!=seq):
        raise JobBlocked('Original owned grass removal unproved; no replay')
    deadline=time.monotonic()+15
    while counts()['minecraft:dirt']==before:
        q=state();drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'and e.get('uuid')not in old_ids
                         and e.get('stack',{}).get('item')=='minecraft:dirt'and e['stack'].get('count')==1
                         and math.dist(e['pos'],pos)<6]
        if len(drops)==1:
            from .dry_hover_harvest import pickup
            pickup(c,drops[0],before,out/'owned-dirt-pickup',state,item='minecraft:dirt');break
        if time.monotonic()>=deadline:raise JobBlocked('Original owned dirt pickup unproved; no replay')
        time.sleep(.15)
    if counts()['minecraft:dirt']!=before+1 or any(r['pos']==pos for r in observe()):raise JobBlocked('Owned grass recovery conservation unproved')
    book['grass_mining_request']=book['pending']['request_id'];book['pending']=None;save()
    c.checked('select_item',item='minecraft:dirt');move(c,[pos[0]+.5,pos[1]+2.2,pos[2]+.5],out/'above-bed',foot_offset=.2)
    book['pending']={'kind':'place_dirt'};save()
    c.checked('interact',pos=base['support']['pos'],face='up',expected_state=base['support']['state'],expected_hand='minecraft:dirt')
    rid=c.last;until(lambda:counts()['minecraft:dirt']==initial-1 and any(r['pos']==pos and block_id(r)=='minecraft:dirt'for r in observe()))
    book['receipts'].append({'kind':'place_dirt','request_id':rid});book['pending']=None;save()
    if next((r for r in state()['inventory']if r.get('slot')==water['slot']),None)!=water:raise JobBlocked('Retained water slot changed during grass recovery')
    c.checked('select_item',item='minecraft:potion',slot=water['slot']);before_water=counts()
    book['pending']={'kind':'water_to_mud'};save()
    c.checked('interact',pos=pos,face='up',expected_state='Block{minecraft:dirt}',expected_hand='minecraft:potion');rid=c.last
    until(lambda:counts()['minecraft:potion']==before_water['minecraft:potion']-1 and counts()['minecraft:glass_bottle']==before_water['minecraft:glass_bottle']+1
          and any(r['pos']==pos and block_id(r)in('minecraft:mud','minecraft:clay')for r in observe()))
    current=refill_column(observe(),pos)
    if not current or not current['filled']or current['support']['state']!=base['support']['state']or current['tip']['state']!=base['tip']['state']:
        raise JobBlocked('Recovered bed support/tip changed')
    book['receipts'].append({'kind':'water_to_mud','request_id':rid});book.update(pending=None,complete=True,dirt_consumed=1,support_preserved=True,tip_preserved=True,mud_mining_sent=False)
    save();return book
