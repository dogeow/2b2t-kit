"""Let the native printer place and fill a pot, confirming both material balances."""
import time
from pathlib import Path
from material_plan import inventory_counts
from projection_completion import block_state
from projection_wood import cell_at
from projection_terrain import FACES
from projection_flat_backend import printer_sent_nothing
from terminal_confirmation import verified
from work_access import approach_faces,ApproachUnavailable
from container_hand import select_container_hand
from kit_runtime.journal import write_json

PLANTS={'minecraft:potted_fern':'minecraft:fern',
        'minecraft:potted_oxeye_daisy':'minecraft:oxeye_daisy'}

def anchors(pos,rows):
    """A pot may use a real wall face; full-cube floor support is not required."""
    by={tuple(v['pos']):v for v in rows};result=[]
    for face in('up','north','south','east','west','down'):
        d=FACES[face];row=by.get(tuple(p-v for p,v in zip(pos,d)))
        if row and row.get('fluid')is False and row.get('block_entity')is False and not row['state'].startswith('Block{minecraft:air}'):
            result.append((face,row))
    return result


def completed_balance(before,after,plant):
    return (after.get('minecraft:flower_pot',0)==before.get('minecraft:flower_pot',0)-1
            and after.get(plant,0)==before.get(plant,0)-1)


def finish(client,targets,out,checkpoint,*,seconds=12):
    """No fallback or replay after an intermediate pot or unconfirmed placement."""
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if not isinstance(targets,list)or not 1<=len(targets)<=16 or len({tuple(p)for p in targets})!=len(targets):
        raise ValueError('A distinct bounded set of original potted plants is required')
    key=client.status()['projection_selection']['key'];results=[]
    for i,p in enumerate(targets):
        checkpoint();audit=client.request('projection_audit')['projection_audit']
        if audit['placement_key']!=key or not audit['loaded_chunks_verified']:raise RuntimeError('Original potted projection changed')
        row=next((r for r in audit['mismatches']if r['pos']==p),None)
        if row is None:continue
        name,props=block_state(row['expected']);plant=PLANTS.get(name)
        if not plant or props or row['kind']!='missing'or row['actual']!='Block{minecraft:air}':
            raise RuntimeError('Potted target requires the exact original empty position')
        scene=client.request('scan',min=[v-1 for v in p],max=[v+1 for v in p],details=True)
        if scene.get('phase')!='done'or scene.get('scan_cells_read')!=27:raise RuntimeError('Current pot wall/support area incomplete')
        options=anchors(p,scene['blocks'])
        if not options:
            results.append({'pos':p,'result':'missing_support'});continue
        before=inventory_counts(client.status())
        if before['minecraft:flower_pot']<1 or before[plant]<1:raise RuntimeError('Actual pot and plant required')
        select_container_hand(client)
        reached=None
        for face,anchor in options:
            try:approach_faces(client,anchor['pos'],anchor['state'],(face,),seconds=25,stand_distance=2.4)
            except ApproachUnavailable:continue
            reached=(face,anchor);break
        if reached is None:
            results.append({'pos':p,'result':'no_visible_support'});continue
        face,anchor=reached;support=anchor['pos']
        checkpoint()
        if cell_at(client,p)['state']!=row['actual']or cell_at(client,support)['state']!=anchor['state']:
            raise RuntimeError('Plant or support changed during approach')
        before=inventory_counts(client.status());client.checked('select_item',item='minecraft:flower_pot')
        client.checked('projection_batch_set',placement_key=key,positions=[p])
        book={'world_session':client.world,'placement_key':key,'pos':p,'plant':plant,
              'inventory_before':dict(before),'pending':'one_bounded_native_pot_and_fill','complete':False}
        path=out/('%02d-progress.json'%i);write_json(path,book)
        reply=client.request('professional_print',seconds=min(30,max(1,seconds)))
        write_json(out/('%02d-native.json'%i),reply)
        zero=printer_sent_nothing(reply,client)
        confirmed=reply.get('phase')=='done'and verified('professional_print',reply,client.world,client.last,{})
        if not zero and not confirmed:raise RuntimeError('Original pot or fill receipt unconfirmed; keep mask and do not replay')
        after=inventory_counts(client.status());actual=cell_at(client,p)['state']
        if zero:
            if actual!=row['actual']or dict(after)!=dict(before):raise RuntimeError('Zero-proposal print changed world or inventory')
        elif actual!=row['expected']or not completed_balance(before,after,plant):
            raise RuntimeError('Potted final state or two-material balance differs; no repeat')
        client.checked('projection_batch_clear',placement_key=key)
        book.update(complete=bool(confirmed),pending=None,inventory_after=dict(after),known_not_sent=zero,actual=actual);write_json(path,book)
        result={'pos':p,'result':'matched'if confirmed else'known_not_sent','plant':plant};results.append(result)
        print('POTTED_PLANT',result,flush=True)
    write_json(out/'results.json',results);return results
