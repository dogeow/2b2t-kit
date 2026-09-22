"""Approach real support faces near unfinished fixtures, then let the existing printer place them."""
import json
from projection_completion import block_state
from projection_terrain import FACES
from work_access import approach_faces,ApproachUnavailable
from goal_workflow import audit

def support_faces(target,expected,observed):
    name,props=block_state(expected);cells={tuple(r['pos']):r for r in observed};options=[]
    directions=['down','up','north','south','east','west']
    if name=='minecraft:lantern' and props.get('hanging')=='true':directions=['down']
    for face in directions:
        delta=FACES[face];pos=tuple(v-d for v,d in zip(target,delta));row=cells.get(pos)
        if row and not row.get('fluid') and block_state(row['state'])[0] not in ('minecraft:air','minecraft:cave_air'):
            options.append((face,row))
    return options

def finish_fixtures(client,targets,seconds=20):
    key=client.status()['projection_selection']['key'];results=[]
    for target in targets:
        if client.status()['projection_selection']['key']!=key:raise RuntimeError('Projection changed during fixture placement')
        current=client.request('projection_audit')['projection_audit'];assert current['placement_key']==key
        row=next((r for r in current['mismatches'] if r['pos']==target),None)
        if row is None:continue
        if row['kind']!='missing':continue
        observed=client.request('scan',min=[v-1 for v in target],max=[v+1 for v in target],details=True)['blocks']
        client.checked('select_item',item='minecraft:diamond_sword');reached=False
        for face,anchor in support_faces(target,row['expected'],observed):
            try:approach_faces(client,anchor['pos'],anchor['state'],(face,),seconds=120,stand_distance=2.4)
            except ApproachUnavailable:continue
            reached=True;break
        if not reached:
            results.append({'target':target,'result':'no_visible_support'});continue
        client.checked('professional_print',seconds=seconds)
        after=audit(client,'fixture-'+','.join(map(str,target)))
        remaining=next((r for r in after['mismatches'] if r['pos']==target),None)
        result={'target':target,'matched_gain':after['matched']-current['matched'],'result':'matched' if remaining is None else 'unresolved','remaining':remaining}
        results.append(result)
        with (client.out/'fixture-results.jsonl').open('a') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
    return results
