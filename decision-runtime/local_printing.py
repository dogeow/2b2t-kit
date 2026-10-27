"""Approach real support faces near unfinished fixtures, then let the existing printer place them."""
import json,time
from pathlib import Path
from projection_completion import block_state
from projection_terrain import FACES
from work_access import approach_faces,ApproachUnavailable
from material_plan import inventory_counts
from container_hand import select_container_hand
from terminal_confirmation import verified
from kit_runtime.journal import write_json

def support_faces(target,expected,observed):
    name,props=block_state(expected);cells={tuple(r['pos']):r for r in observed};options=[]
    directions=['down','up','north','south','east','west']
    if name=='minecraft:lantern' and props.get('hanging')=='true':directions=['down']
    if name.endswith(('_carpet','_candle'))or name in ('minecraft:flower_pot','minecraft:candle','minecraft:anvil'):
        directions=['up']
    if name=='minecraft:tripwire_hook':directions=[props['facing']]
    if name.endswith('_wall_banner') and props.get('facing')in('north','south','east','west'):
        directions=[props['facing']]
    if name.endswith('_trapdoor') and props.get('facing') in ('north','south','east','west'):
        directions=[props['facing']]
    for face in directions:
        delta=FACES[face];pos=tuple(v-d for v,d in zip(target,delta));row=cells.get(pos)
        if row and not row.get('fluid') and block_state(row['state'])[0] not in ('minecraft:air','minecraft:cave_air'):
            options.append((face,row))
    return options

def finish_fixtures(client,targets,seconds=20,*,approach=True):
    from projection_flat_backend import printer_sent_nothing
    key=client.status()['projection_selection']['key'];world=client.world;results=[]
    for target in targets:
        if client.status()['projection_selection']['key']!=key or client.world!=world:raise RuntimeError('Projection changed during fixture placement')
        current=client.request('projection_audit')['projection_audit'];assert current['placement_key']==key
        row=next((r for r in current['mismatches'] if r['pos']==target),None)
        if row is None:continue
        if row['kind']!='missing':continue
        item=block_state(row['expected'])[0]
        if item.endswith('_wall_banner'):item=item.removesuffix('_wall_banner')+'_banner'
        if inventory_counts(client.status()).get(item,0)<1:
            results.append({'target':target,'result':'no_carried_material','item':item});continue
        observed=client.request('scan',min=[v-1 for v in target],max=[v+1 for v in target],details=True)['blocks']
        supports=support_faces(target,row['expected'],observed)
        reached=bool(supports)if not approach else False
        if approach:
            select_container_hand(client)
            for face,anchor in supports:
                try:approach_faces(client,anchor['pos'],anchor['state'],(face,),seconds=30,stand_distance=2.4)
                except ApproachUnavailable:continue
                reached=True;break
        if not reached:
            results.append({'target':target,'result':'no_visible_support'});continue
        out=Path(client.out)/('fixture-'+','.join(map(str,target))+'-'+str(time.time_ns()));out.mkdir()
        before=inventory_counts(client.status()).get(item,0)
        if before<1:raise RuntimeError('Fixture material changed during approach; no print sent')
        client.checked('select_item',item=item)
        client.checked('projection_batch_set',placement_key=key,positions=[target])
        book={'world_session':world,'placement_key':key,'target':target,'item':item,
              'inventory_before':before,'pending':'one_bounded_professional_print','complete':False}
        write_json(out/'progress.json',book)
        reply=client.request('professional_print',seconds=min(30,max(1,seconds)))
        write_json(out/'native-printer-receipt.json',reply)
        no_effect=printer_sent_nothing(reply,client)
        confirmed=reply.get('phase')=='done' and verified('professional_print',reply,world,client.last,{})
        if not confirmed and not no_effect:
            raise RuntimeError('Original fixture print remains unconfirmed; retain receipt without retry or mask clear')
        after=client.request('projection_audit')['projection_audit']
        if after['placement_key']!=key:raise RuntimeError('Projection changed during fixture verification')
        remaining=next((r for r in after['mismatches'] if r['pos']==target),None)
        actual_count=inventory_counts(client.status()).get(item,0)
        if no_effect:
            if remaining!=row or actual_count!=before:raise RuntimeError('Zero-proposal fixture interval changed cell or stock; retain journal')
        elif remaining is not None or actual_count!=before-1:
            raise RuntimeError('Fixture server receipt and physical/stock result differ; no repeated print')
        client.checked('projection_batch_clear',placement_key=key)
        book.update(pending=None,complete=confirmed,known_not_sent=no_effect,inventory_after=actual_count)
        write_json(out/'progress.json',book)
        result={'target':target,'matched_gain':after['matched']-current['matched'],'result':'matched' if remaining is None else 'unresolved','remaining':remaining,'known_not_sent':no_effect}
        results.append(result)
        with (client.out/'fixture-results.jsonl').open('a') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
    return results
