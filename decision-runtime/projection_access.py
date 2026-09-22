"""Open an observed trapdoor directly above the selected design's ladder shaft."""
import json
from projection_completion import block_state


def open_ladder_hatch(client, column):
    state=client.status()
    audit=client.request('projection_audit')['projection_audit']
    if audit['placement_key']!=state['projection_selection']['key']:
        raise RuntimeError('Projection changed before opening basement access')
    saved_path=client.out/'basement-hatch.json'
    saved=json.loads(saved_path.read_text()) if saved_path.exists() else {}
    known=saved.get('after',{})
    cached=saved.get('placement_key')==audit['placement_key'] and len(known.get('pos',[]))==3 and [known['pos'][0],known['pos'][2]]==column
    ladders=[r for r in audit['mismatches'] if r['pos'][0]==column[0] and r['pos'][2]==column[1]
             and block_state(r['expected'])[0]=='minecraft:ladder']
    if not ladders and not cached:return None
    if cached:low=high=known['pos']
    else:
        top=max(r['pos'][1] for r in ladders)
        low=[column[0],top+1,column[1]];high=[column[0],top+2,column[1]]
    rows=client.request('scan',min=low,max=high,details=True)['blocks']
    hatches=[r for r in rows if block_state(r['state'])[0].endswith('_trapdoor') and not r['fluid']]
    if len(hatches)!=1:raise RuntimeError('Expected ladder hatch was not uniquely observed')
    row=hatches[0];_,properties=block_state(row['state'])
    if properties.get('open')=='true':
        saved_path.write_text(json.dumps({'placement_key':audit['placement_key'],'before':row,'after':row}))
        return row
    if properties.get('open')!='false':raise RuntimeError('Unknown hatch state')
    face='down' if client.status()['pos'][1]<row['pos'][1] else 'up'
    client.checked('approach_block',pos=row['pos'],face=face,expected_state=row['state'],seconds=120)
    client.checked('select_item',item='minecraft:diamond_sword')
    client.checked('interact',pos=row['pos'],face=face,expected_state=row['state'],expected_hand='minecraft:diamond_sword')
    observed=client.request('scan',min=row['pos'],max=row['pos'],details=True)['blocks']
    if len(observed)!=1 or block_state(observed[0]['state'])[1].get('open')!='true':
        raise RuntimeError('Hatch opening was not confirmed; do not toggle it again')
    saved_path.write_text(json.dumps({'placement_key':audit['placement_key'],'before':row,'after':observed[0]},ensure_ascii=False,indent=2))
    print('HATCH_OPEN',row['pos'],flush=True)
    return observed[0]
