"""Independent current-cell restoration after a fully acknowledged old harvest.

Old harvest/mud journals are never marked successful or replayed. A new proof
can advance the field's active pointer only after new seed/crop conservation.
"""
import hashlib
import json
from pathlib import Path
import time
import math

from kit_runtime.journal import write_json
from material_plan import inventory_counts
from potato_harvest import _registered_wheat
from potato_loot_flight import make_plant_access
from potato_farm import plan
from .protocol import JobBlocked, server_key
from potato_farm import FarmWait


def current_existing_cell(client,pos,state):
    """Prove only this historical target; unrelated field changes stay unresolved."""
    times=[];frames=[];counts=inventory_counts(state);before=state['time']
    for _ in range(2):
        reply=client.checked('scan',min=pos,max=[pos[0],pos[1]+1,pos[2]],details=True)
        rows={tuple(r['pos']):r for r in reply.get('blocks',[])}
        floor=rows.get(tuple(pos),{});crop=rows.get((pos[0],pos[1]+1,pos[2]),{})
        text=crop.get('state','');prefix='Block{minecraft:wheat}[age='
        age=text[len(prefix):-1]if text.startswith(prefix)and text.endswith(']')else''
        if (reply.get('phase')!='done' or reply.get('world_session')!=client.world
                or reply.get('scan_cells_read')!=2 or reply.get('scan_total_cells')!=2
                or reply.get('scan_start_revision')!=client.rev or reply.get('scan_end_revision')!=client.rev
                or reply.get('time',0)<=before or inventory_counts(client.status())!=counts
                or not floor.get('state','').startswith('Block{minecraft:farmland}[moisture=')
                or floor.get('fluid')is not False or floor.get('block_entity')is not False
                or not age.isdigit()or not 0<=int(age)<=7
                or crop.get('fluid')is not False or crop.get('block_entity')is not False):
            raise JobBlocked('当前原格的两帧耕地与麦子没有完整核验；不更新指针')
        before=reply['time'];times.append(before);frames.append({'time':before,'floor':floor,'crop':crop})
    return frames


def historical_removal(book, reply, state):
    pending=book.get('pending')or{};receipt=pending.get('native_mining_receipt')or{}
    pos=pending.get('pos');old_world=book.get('world_session')
    keys=('id','world_session','phase','server_confirmed','outcome_pending','confirmation_scope',
          'server_update_seen','server_observed_state','native_sequence','server_ack_sequence','mining_target')
    if (pending.get('operation')!='await_loot' or pending.get('native_mining_confirmed')is not True
            or pending.get('crop_removed')is not True or not isinstance(pos,list) or len(pos)!=3
            or any(type(v)is not int for v in pos) or old_world==state.get('world_session')
            or not old_world or receipt.get('world_session')!=old_world
            or any(reply.get(k)!=receipt.get(k)for k in keys)
            or receipt.get('phase')!='done' or receipt.get('server_confirmed')is not True
            or receipt.get('outcome_pending')is not False or receipt.get('server_update_seen')is not True
            or receipt.get('server_observed_state')!='Block{minecraft:air}'
            or receipt.get('mining_target')!=[pos[0],pos[1]+1,pos[2]]
            or type(receipt.get('native_sequence'))is not int
            or receipt.get('server_ack_sequence',-1)<receipt['native_sequence']
            or reply.get('player_uuid')!=state.get('player_uuid')
            or server_key(reply.get('server'))!=server_key(state.get('server'))
            or reply.get('dimension')!=state.get('dimension') or state.get('dimension')!='minecraft:overworld'):
        raise JobBlocked('原麦子移除的完整服务器回执或当前角色无法核验；不补种或改指针')
    return pending,pos


def run(client, journal, out, checkpoint=lambda:None, *, pickup_proof=None):
    from .registered_wheat import registered_fields
    from work_access import approach_faces
    journal=Path(journal);out=Path(out)
    if out.exists():raise ValueError('Use a new independent wheat restoration directory')
    raw=journal.read_bytes();book=json.loads(raw);pending=book.get('pending')or{}
    rid=(pending.get('receipt')or{}).get('id')
    if not isinstance(rid,str)or not rid.startswith('materials-'):
        raise JobBlocked('原麦子请求身份缺失')
    original_reply=json.loads((Path(client.root)/('reply-'+rid+'.json')).read_text())
    state=client.status();pending,pos=historical_removal(book,original_reply,state)
    registered=next(((q,r,plan(q))for q,r in registered_fields(client)if pos in plan(q)['cells']),None)
    if registered is None:raise JobBlocked('原空格不属于完整登记小麦田')
    request,registry,layout=registered;request={**request,'cells':layout['cells']}
    pointer=registry.parent/'harvest-active.json';pointer_raw=pointer.read_bytes();active=json.loads(pointer_raw)
    if Path(active['journal']).resolve()!=journal.resolve():raise JobBlocked('原活动收麦记录已变化')
    if sum((a-b)**2 for a,b in zip(state['pos'],pos))>100:
        raise JobBlocked('独立补种只在原田附近执行')
    grain=inventory_counts(state)['minecraft:wheat']
    expected=pending['before_counts'].get('minecraft:wheat',0)+pending.get('observed_drop_totals',{}).get('minecraft:wheat',0)
    extra_stock_proved=False
    if pickup_proof is not None:
        capture=json.loads(Path(pickup_proof).read_text())
        known={d['uuid']:d for d in pending.get('owned_loot',[])}
        drop=known.get(capture.get('drop_uuid'))or{}
        extra_stock_proved=(capture.get('picked')is True and capture.get('source_absent')is True
            and capture.get('no_crop_mined')is True and drop.get('item')=='minecraft:wheat'
            and capture.get('after')==capture.get('before',-1)+drop.get('count',0)
            and capture.get('before')==pending['before_counts'].get('minecraft:wheat',0)
            and capture.get('after')==expected)
    if (grain!=expected and not extra_stock_proved) or any(e.get('uuid')in {d['uuid']for d in pending.get('current_loot',[])}for e in state.get('entities',[])):
        raise JobBlocked('原粮食没有以当前实际库存和已知掉落消失核验；不补种')
    # Borrow existing full-field two-frame validation. The native removal
    # above stays explicitly historical; no current mining receipt is invented.
    initial=client.checked('scan',min=pos,max=[pos[0],pos[1]+1,pos[2]],details=True)
    existing=next((r for r in initial['blocks']if r['pos']==[pos[0],pos[1]+1,pos[2]]),None)
    already_restored=existing is not None and existing['state'].startswith('Block{minecraft:wheat}[age=')
    whole_field_verified=True;field_limit=None;cell_frames=None
    try:_registered_wheat(client,request,journal,known_replant=None if already_restored else pos,bind_active=False)
    except FarmWait as error:
        if not already_restored or error.code not in ('WAIT_SOIL','WAIT_EXISTING_FARMLAND'):
            raise
        cell_frames=current_existing_cell(client,pos,client.status())
        whole_field_verified=False;field_limit={'code':error.code,'detail':str(error)}
    out.mkdir(parents=True);(out/'original-harvest-unchanged.json').write_bytes(raw)
    (out/'original-active-pointer.json').write_bytes(pointer_raw)
    proof={'schema':1,'kind':'independent_registered_cell_restore','world_session':client.world,
           'scope':json.loads(registry.read_text())['scope'],'historical_harvest':str(journal.resolve()),
           'historical_harvest_sha256':hashlib.sha256(raw).hexdigest(),'historical_receipt_reclassified':False,
           'old_harvest_replayed':False,'grain_inventory_credit':0,'pos':pos,'pending':None,'complete':False}
    proof['additional_current_stock_not_old_harvest_credit']=max(0,grain-expected)
    proof['historically_recovered_grain_may_be_stored']=extra_stock_proved and grain<expected
    proof.update(whole_registered_field_verified=whole_field_verified,field_maintenance_required=field_limit,
                 verification_scope='original_single_harvested_cell'if not whole_field_verified else'complete_registered_field')
    path=out/'current-cell-restoration.json';write_json(path,proof)
    if already_restored:
        if journal.read_bytes()!=raw or pointer.read_bytes()!=pointer_raw:
            raise JobBlocked('原记录变化；不更新当前田地指针')
        proof.update(complete=True,new_reseed=0,current_existing_crop_verified=True,original_harvest_bytes_unchanged=True,
                     current_cell_frames=cell_frames)
        write_json(path,proof)
        write_json(pointer,{'schema':1,'scope':proof['scope'],'world_session':client.world,'journal':str(path.resolve()),
                            'historical_pending_preserved':str(journal.resolve()),'current_independent_restoration':True})
        return proof
    checkpoint();make_plant_access(layout['center'],radius=layout['radius'],checkpoint=checkpoint)(client,pos,client.status(),'before_plant')
    rows=client.checked('scan',min=pos,max=[pos[0],pos[1]+1,pos[2]],details=True)['blocks']
    floor=next((r for r in rows if r['pos']==pos),None)
    if (floor is None or not floor['state'].startswith('Block{minecraft:farmland}')
            or floor.get('fluid')is not False or any(r['pos'][1]>pos[1]for r in rows)):
        raise JobBlocked('当前原空格已改变；不放置新种子')
    client.checked('select_item',item='minecraft:wheat_seeds')
    approach_faces(client,pos,floor['state'],('up',),seconds=45)
    before=client.status();counts=inventory_counts(before)
    if counts['minecraft:wheat_seeds']<5:raise JobBlocked('独立补种保留四粒种子')
    proof['pending']={'kind':'new_seed_use','before':dict(counts)};write_json(path,proof)
    reply=client.request('interact',pos=pos,face='up',expected_state=floor['state'],expected_hand='minecraft:wheat_seeds')
    proof['pending']['native_receipt']=reply;write_json(path,proof)
    if reply.get('phase')!='done':raise JobBlocked('新补种动作尚未确认；保留新记录，不重放')
    frames=[];deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        checkpoint();scan=client.checked('scan',min=pos,max=[pos[0],pos[1]+1,pos[2]],details=True)
        after=client.status();now=inventory_counts(after);rows=scan['blocks']
        changed={i:now[i]-counts[i]for i in now.keys()|counts.keys()if now[i]!=counts[i]}
        if (changed=={'minecraft:wheat_seeds':-1}
                and any(r['pos']==[pos[0],pos[1]+1,pos[2]]and r['state']=='Block{minecraft:wheat}[age=0]'for r in rows)
                and (not frames or scan['time']>frames[-1]['time'])):
            frames.append({'time':scan['time'],'counts':dict(now),'crop_state':'Block{minecraft:wheat}[age=0]'})
        if len(frames)>=2:break
        time.sleep(.15)
    if len(frames)<2:raise JobBlocked('新种子扣一和两帧年龄零麦子尚未核验；保留新记录')
    _registered_wheat(client,request,journal,bind_active=False)
    if journal.read_bytes()!=raw or pointer.read_bytes()!=pointer_raw:
        raise JobBlocked('原记录变化；不更新当前田地指针')
    proof.update(pending=None,complete=True,new_reseed=1,frames=frames,original_harvest_bytes_unchanged=True)
    write_json(path,proof)
    write_json(pointer,{'schema':1,'scope':proof['scope'],'world_session':client.world,'journal':str(path.resolve()),
                        'historical_pending_preserved':str(journal.resolve()),'current_independent_restoration':True})
    return proof
