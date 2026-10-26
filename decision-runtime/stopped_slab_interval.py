"""Prove a stopped partial bottom-slab interval has no outstanding placement input.

Never marks the old mask complete, rewrites its journal, rebinds a world, or
replays an action. A caller may release only these same-world reservations.
"""
import math
from material_plan import inventory_counts
from roof_slab_window_plan import SLAB
HOST_HASHES={
 'printer':'ec9e17f05209d36f2eb0666abdcf65a7cf4fbacf1be916c2c06f33b64bbd1046',
 'batch':'f641dbbaa0337d756ef043b59c5be0602df277ef398bded40c2592c5b219b0fb',
 'pacer':'47d5957c2f9d1e53bce3884fe335bca6d4d07fb3f217e73f26afbb4c59c21ac5',
 'state':'46a42e5146094034c1c88bf18fdf06053c6fb409d4dbd88fbd9cc2cb0aa9da3d',
 'bridge':'2d2ec0966d64897008facd673607411635a448c02d5d9a6586ec6d5242cc9c44'}

def prove(proof,before_scan,before_snapshot,*,world,hashes,before_intent):
    r=proof['original_reply'];u=proof['original_request'];p=r['professional_printer'];mask=r['bounded_targets'];k=p['server_confirmed'];frames=proof['frames']
    if(hashes!=HOST_HASHES or not world or r['world_session']!=u['world_session']or world!=r['world_session']
            or u['op']!='professional_print'or r['id']!=u['request_id']or not u['request_id']
            or r['phase']!='stopped'or r['detail']!='托管收尾，等待脱离战斗'
            or r['server_confirmed']is not False or r['outcome_pending']is not True
            or r['bounded_target_count']!=len(mask)or len(set(map(tuple,mask)))!=len(mask)
            or any(len(v)!=3 or any(type(n)is not int for n in v)for v in mask)
            or type(k)is not int or not 0<k<len(mask)or p['fast_proposals']!=0 or p['complex_proposals']!=k
            or p['enabled']is not False or p['owned']is not False or p['waiting_for_server']is not False
            or p['travel_pending']!=0 or p['failure']!=''or len(frames)!=2):
        raise ValueError('Stopped acknowledged same-world slab interval is unproved')
    last=p['last_proposal']
    if(any(last.get(key)is not True for key in ['interaction_seen','interaction_matches_proposal','server_update_seen','ack_final'])
            or any(last.get(key)!=SLAB for key in ['expected','final_target','server_update_state','ack_actual'])
            or type(last.get('sent_tick'))is not int or type(last.get('server_update_tick'))is not int
            or not 0<=last['sent_tick']<=last['server_update_tick']):raise ValueError('Final queued placement lacks its own server ACK')
    volume=math.prod(max(v[i]for v in mask)-min(v[i]for v in mask)+1 for i in range(3))
    low=[min(v[i]for v in mask)for i in range(3)];high=[max(v[i]for v in mask)for i in range(3)]
    if(before_intent.get('op')!='scan'or before_intent.get('id')!=before_scan.get('id')
            or before_intent.get('world_session')!=world or before_intent.get('task_session')!=u['task_session']
            or before_intent.get('min')!=low or before_intent.get('max')!=high or before_intent.get('details')is not True
            or before_intent.get('expected_revision')!=before_scan['scan_start_revision']):raise ValueError('Original scan intent does not cover the exact mask')
    if(before_scan['world_session']!=world or before_snapshot['world_session']!=world
            or before_scan['phase']!='done'or before_snapshot['phase']!='done'
            or before_scan['scan_cells_read']!=volume or before_scan['scan_total_cells']!=volume or before_scan['blocks']
            or before_scan['scan_start_revision']!=before_scan['scan_end_revision']or before_scan['scan_end_revision']!=before_snapshot['control_revision']):raise ValueError('Original empty mask is unproved')
    inventory=dict(inventory_counts(before_snapshot));item='minecraft:cobblestone_slab';inventory[item]=inventory.get(item,0)-k
    if inventory[item]<0:raise ValueError('Material debit is impossible')
    inventory={key:value for key,value in inventory.items()if value};matched=None;time=r['time']
    for f in frames:
        lease=f.get('supervision_lease')or{};rows=f['blocks'];positions={tuple(v['pos'])for v in rows}
        if(f['world_session']!=world or f['health']!=20 or f['connected']is not True or f['screen']!=''or f['manual_movement']is not False
                or f['scan_cells_read']!=volume or f['scan_total_cells']!=volume or f['scan_start_revision']!=f['scan_end_revision']
                or f['time']<=time or f['professional_printer']!=p or dict(inventory_counts(f))!=inventory
                or lease.get('world_session')!=world or lease.get('job_session')!=u['task_session']or lease.get('id')!=u['lease_id']
                or lease.get('revision')!=f['control_revision']or f['scan_end_revision']!=f['control_revision']
                or len(rows)!=k or len(positions)!=k or not positions<=set(map(tuple,mask))
                or any(v['state']!=SLAB or v.get('fluid')is not False or v.get('block_entity')is not False for v in rows)
                or matched is not None and positions!=matched):raise ValueError('Current cells, queue and material debit do not agree')
        matched=positions;time=f['time']
    return {'classification':'same_world_stopped_partial_bottom_slab_all_queued_inputs_acknowledged',
            'request_id':r['id'],'world_session':world,'original_mask_complete':False,
            'acknowledged_positions':[v for v in mask if tuple(v)in matched],
            'never_attempted_positions':[v for v in mask if tuple(v)not in matched],
            'releasable_reservations':mask,'old_request_replayed':False,'world_rebound':False}
