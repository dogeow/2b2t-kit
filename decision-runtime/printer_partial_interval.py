"""Resolve only a pinned plain-cube interval whose every queued proposal ACKed.

The host's outcome_pending is !whole_mask_complete, including never-attempted
cells. Equal monotonic queued/ACK counters, exact inventory conservation and
two current scans can prove no outstanding input without declaring the old
mask complete. A sent-but-unacknowledged proposal always remains unresolved.
An unattempted short-grass cell must remain identical in both scans and never
counts toward the acknowledged plain-cube placements.
"""
from copy import deepcopy
from material_plan import inventory_counts

HOST_HASHES={
 'jar':'d51d980dd68ea9f76e0d00c531d2b903657e3879d5ac5b91ff3a47d39ad9653a',
 'printer':'ec9e17f05209d36f2eb0666abdcf65a7cf4fbacf1be916c2c06f33b64bbd1046',
 'batch':'f641dbbaa0337d756ef043b59c5be0602df277ef398bded40c2592c5b219b0fb',
 'pacer':'47d5957c2f9d1e53bce3884fe335bca6d4d07fb3f217e73f26afbb4c59c21ac5'}
REASON='printer interval ended without complete current bounded-mask server confirmation'
AIR_STATES=('Block{minecraft:air}','Block{minecraft:cave_air}','Block{minecraft:void_air}')
SHORT_GRASS='Block{minecraft:short_grass}'

def prove(pending,reply,before_audit,frames,hashes):
    positions=pending.get('positions')or[];item=pending.get('item');p=reply.get('professional_printer')or{};n=p.get('server_confirmed');world=reply.get('world_session');key=reply.get('placement_key');owner=reply.get('supervision_lease')or{}
    if(hashes!=HOST_HASHES or reply.get('phase')!='waiting'or reply.get('detail')!=REASON
            or reply.get('server_confirmed')is not False or reply.get('outcome_pending')is not True
            or not world or not key or len(frames)!=2 or not positions or len({tuple(v)for v in positions})!=len(positions)
            or any(not isinstance(v,list)or len(v)!=3 or any(type(n)is not int for n in v)for v in positions)
            or owner.get('kind')!='materials'or not owner.get('id')or owner.get('world_session')!=world
            or {tuple(v)for v in reply.get('bounded_targets',[])}!={tuple(v)for v in positions}
            or reply.get('bounded_target_count')!=len(positions)or type(n)is not int or not 0<n<len(positions)
            or type(p.get('fast_proposals'))is not int or p['fast_proposals']!=n or type(p.get('complex_proposals'))is not int or p['complex_proposals']!=0
            or p.get('enabled')is not False or p.get('owned')is not False or p.get('waiting_for_server')is not False
            or p.get('travel_pending')!=0 or p.get('failure')!=''
            or(p.get('last_proposal')or{}).get('ack_final')is not True
            or before_audit.get('placement_key')!=key):
        raise RuntimeError('All queued plain-cube proposals are not independently acknowledged')
    expected='Block{'+str(item)+'}';prior={tuple(v['pos']):v for v in before_audit.get('mismatches',[])}
    if any(prior.get(tuple(v),{}).get('kind')!='missing'or prior[tuple(v)].get('expected')!=expected
           or prior[tuple(v)].get('actual')not in AIR_STATES+(SHORT_GRASS,)for v in positions):
        raise RuntimeError('Exact original empty plain-cube mask is unproved')
    plants=[v for v in positions if prior[tuple(v)]['actual']==SHORT_GRASS]
    if any(prior[tuple(v)].get('block_entity')is not False or prior[tuple(v)].get('fluid')is not False
           or prior[tuple(v)].get('neighbors_loaded')is not True or prior[tuple(v)].get('adjacent_fluid')is not False for v in plants):
        raise RuntimeError('Remaining grass lacks a complete safe original observation')
    after=dict(pending['before']);after[item]-=n;after={k:v for k,v in after.items()if v};last=reply.get('time');matched=None;times=[];volume=1
    for i in range(3):volume*=max(v[i]for v in positions)-min(v[i]for v in positions)+1
    for f in frames:
        rows={tuple(v['pos']):v for v in f.get('blocks',[])};current=[]
        if(f.get('world_session')!=world or f.get('connected')is not True or f.get('health')!=20
                or f.get('manual_movement')is not False or f.get('screen')!=''or f.get('professional_printer')!=p
                or any((f.get('supervision_lease')or{}).get(k)!=owner.get(k)for k in('id','kind','job_session','world_session'))
                or(f.get('projection_selection')or{}).get('key')!=key or f.get('menu',{}).get('cursor',{}).get('count')!=0
                or f.get('scan_cells_read')!=volume or f.get('scan_total_cells')!=volume or f.get('unloaded_chunks',0)
                or type(last)is not int or f.get('time',0)<=last or dict(inventory_counts(f))!=after):
            raise RuntimeError('Current stopped printer and conserved material observations are unproved')
        for pos in positions:
            row=rows.get(tuple(pos));state=(row or{}).get('state','Block{minecraft:air}')
            if state==expected:
                if prior[tuple(pos)]['actual']not in AIR_STATES:
                    raise RuntimeError('A non-air target changed; plain-cube input proof does not cover it')
                current.append(pos)
            elif pos in plants:
                if state!=SHORT_GRASS:raise RuntimeError('Original unattempted grass did not remain unchanged')
            elif state not in AIR_STATES:
                raise RuntimeError('A remaining target has an unrelated current obstacle')
        if len(current)!=n or matched is not None and current!=matched:raise RuntimeError('Distinct current fulfilled cells differ from native ACK count')
        matched=current;last=f['time'];times.append(last)
    return {'schema':1,'classification':'all_queued_plain_cube_proposals_acknowledged_partial_mask',
        'request_id':reply['id'],'world_session':world,'placement_key':key,'host_hashes':deepcopy(hashes),
        'original_outcome_pending_flag':True,'original_mask_complete':False,'acknowledged_proposals':n,
        'current_fulfilled_positions':deepcopy(matched),'remaining_current_missing':[v for v in positions if v not in matched],
        'remaining_unchanged_short_grass':deepcopy(plants),
        'material_debit':n,'observed_times':times,'original_request_replayed':False}
