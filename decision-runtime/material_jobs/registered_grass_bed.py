"""Recover grass only on an explicitly registered owned conversion bed."""
import math,time
from pathlib import Path
from kit_runtime.journal import write_json
from work_access import approach_faces
from material_trip_policy import room_for_item
from .acquisition import _safe,_scan,_tool,_choose_tool,carried,block_id
from .mud_conversion import refill_column
from .dry_hover_harvest import pickup
from .direct_clay_refill import refill
from .protocol import JobBlocked


def run(c,pos,profile,out,checkpoint):
    cfg=profile.get('clay_conversion_farm')or{}
    if cfg.get('authorized')is not True or pos not in cfg.get('positions',[]):
        raise JobBlocked('Grass recovery needs an explicitly registered conversion bed')
    out=Path(out);out.mkdir(parents=True,exist_ok=True);path=out/'grass-bed.json'
    if path.exists():raise JobBlocked('Original registered-grass recovery retained; no replay')
    def state():checkpoint();q=c.status();_safe(q);return q
    def observe():return _scan(c,[pos[0],pos[1]-2,pos[2]],pos,state)
    rows=observe();top=next((r for r in rows if r['pos']==pos),None)
    base=refill_column([r for r in rows if r['pos']!=pos],pos)
    if (not top or block_id(top)!='minecraft:grass_block'or top.get('fluid')is not False
            or top.get('block_entity')is not False or not base):
        raise JobBlocked('Registered grass/full support/true tip are not currently proved')
    if room_for_item(state(),'minecraft:dirt')<1:raise JobBlocked('No room for the exact recovered grass dirt')
    tool=_tool(state(),'shovel',33,no_silk=True)
    if any(e.get('id')=='minecraft:silk_touch'for e in tool.get('enchantments',[])):
        raise JobBlocked('Grass recovery needs an ordinary non-silk shovel')
    face=approach_faces(c,pos,top['state'],('up',),seconds=45,stand_distance=1.2)
    _choose_tool(c,tool,state)
    fresh=observe();current=next((r for r in fresh if r['pos']==pos),None)
    fresh_base=refill_column([r for r in fresh if r['pos']!=pos],pos)
    if (not current or current.get('state')!=top['state']or current.get('fluid')is not False
            or current.get('block_entity')is not False or not fresh_base or fresh_base['support']['state']!=base['support']['state']
            or fresh_base['tip']['state']!=base['tip']['state']):
        raise JobBlocked('Registered grass bed changed before mining')
    q=state();before=carried(q,'minecraft:dirt');old={e['uuid']for e in q.get('entities',[])if e.get('type')=='minecraft:item'}
    book={'world_session':c.world,'pos':pos,'initial_carried_dirt':before,'soil_origin':'registered_existing_bed',
          'pending':'mine_registered_grass','complete':False};write_json(path,book)
    try:reply=c.checked('mine_block',pos=pos,face=face,expected_state=top['state'],seconds=20)
    finally:book['request_id']=c.last;write_json(path,book)
    seq=reply.get('native_sequence');write_json(out/'grass-mining-receipt.json',reply)
    if (reply.get('id')!=c.last or reply.get('world_session')!=c.world or reply.get('phase')!='done'
            or reply.get('mining_target')!=pos or reply.get('server_confirmed')is not True
            or reply.get('confirmation_scope')!='single_target_server_block_update_and_native_sequence_ack'
            or type(seq)is not int or seq<=0 or reply.get('server_ack_sequence')!=seq):
        raise JobBlocked('Original grass mining ACK unconfirmed; no replay')
    until=time.monotonic()+15
    while carried(state(),'minecraft:dirt')==before:
        q=state();drops=[e for e in q.get('entities',[])if e.get('type')=='minecraft:item'and e.get('uuid')not in old
                         and e.get('stack',{}).get('item')=='minecraft:dirt'and e['stack'].get('count')==1
                         and math.dist(e['pos'],pos)<6]
        if len(drops)==1:
            pickup(c,drops[0],before,out/'exact-grass-dirt-pickup',state,item='minecraft:dirt');break
        if time.monotonic()>=until:raise JobBlocked('Original grass dirt pickup unproved; no mining replay')
        time.sleep(.15)
    if carried(state(),'minecraft:dirt')!=before+1 or any(r['pos']==pos for r in observe()):
        raise JobBlocked('Original grass removal and one recovered dirt are not proved')
    book.update(pending='distinct_soil_refill',actual_dirt_recovered=1);write_json(path,book)
    result=refill(c,pos,profile,out/'distinct-soil-refill',state)
    final=refill_column(observe(),pos)
    if (result.get('complete')is not True or carried(state(),'minecraft:dirt')!=before
            or not final or not final['filled']or final['support']['state']!=base['support']['state']
            or final['tip']['state']!=base['tip']['state']):
        raise JobBlocked('Registered grass replacement conservation unconfirmed; no replay')
    book.update(pending=None,complete=True,dirt_net_consumed=0,distinct_refill=result,
                support_preserved=True,tip_preserved=True);write_json(path,book);return book
