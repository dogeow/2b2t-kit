"""Read-only proof of the pinned printer's settled first-half admission failure.

An incomplete mask is not completion. This only retires reservations after the
native job reports a settled queue, all queued actions ACKed, and two original
same-world whole-scene scans account for every slab and every changed block.
No game input, request replay, owner restoration, or world relabeling happens.
"""
from copy import deepcopy
import math
from material_plan import inventory_counts

HOST_HASHES={'jar': '67b8ffa40f1cd06d8b986130764583cf99313324bbf46f05356949a885ab7ad4', 'ProfessionalPrinter': '0f1b47d6040a1cf9af4b811238f72d094a8f48ad471ae670d7bf7e74af3b4e5a', 'PrinterSlabPlacement': 'af6283bb7205048b224dd78a91c0b00fe64f62730f7057e50fb720bff05df99a', 'ProjectionBuildJob': 'fd16f7be9184a678964f2d7ffbaa94d879649e30f273b22592b1a78137738c86'}
DOUBLE='Block{minecraft:cobblestone_slab}[type=double,waterlogged=false]'
HALVES={f'Block{{minecraft:cobblestone_slab}}[type={half},waterlogged=false]'for half in ['bottom','top']}
FAILURE='打印器接口不兼容，已停止放置'

def prove(mask,before,frames,model,intent,hashes):
    if hashes!=HOST_HASHES or len(frames)!=2:raise RuntimeError('Pinned host and two original observations required')
    if not mask or any(not isinstance(p,list)or len(p)!=3 or any(type(n)is not int for n in p)for p in mask):raise RuntimeError('Exact distinct original mask required')
    targets=set(map(tuple,mask))
    if len(targets)!=len(mask):raise RuntimeError('Duplicate original targets')
    world=before.get('world_session');key=model.get('placement_key');owner=before.get('supervision_lease')or{}
    expected={tuple(v['pos']):v['state']for v in model.get('expected',[])}
    if not world or not key or model.get('loaded_server_chunks_verified')is not True or any(expected.get(p)!=DOUBLE for p in targets):raise RuntimeError('Original double-slab projection is unproved')
    low,high=intent.get('min'),intent.get('max')
    if (not isinstance(low,list)or not isinstance(high,list)or len(low)!=3 or len(high)!=3
            or any(type(n)is not int for n in low+high)or any(a>b for a,b in zip(low,high))
            or intent.get('op')!='scan'or intent.get('details')is not True or intent.get('id')!=before.get('id')
            or intent.get('world_session')!=world or intent.get('task_session')!=owner.get('job_session')
            or intent.get('expected_revision')!=before.get('control_revision')):raise RuntimeError('Original scan bounds and request identity required')
    volume=math.prod(b-a+1 for a,b in zip(low,high))
    def rows(frame):
        if (frame.get('phase')!='done'or frame.get('scan_cells_read')!=volume or frame.get('scan_total_cells')!=volume
                or frame.get('scan_start_revision')!=frame.get('scan_end_revision')or frame.get('unloaded_chunks',0)
                or frame.get('world_session')!=world or frame.get('kit_version')!='2026.10.26.2'
                or frame.get('connected')is not True or frame.get('health')!=20 or frame.get('manual_movement')is not False
                or frame.get('screen')!=''or (frame.get('projection_selection')or{}).get('key')!=key
                or frame.get('menu',{}).get('cursor',{}).get('count')!=0):raise RuntimeError('Complete healthy original same-world frame required')
        lease=frame.get('supervision_lease')or{}
        if (lease.get('kind')!='materials'or lease.get('revision')!=frame.get('control_revision')
                or any(lease.get(k)!=owner.get(k)for k in ['id','job_session','world_session'])):raise RuntimeError('Original owner scope changed')
        result={}
        for row in frame.get('blocks',[]):
            p=row.get('pos')
            if (not isinstance(p,list)or len(p)!=3 or any(type(n)is not int for n in p)
                    or not all(a<=n<=b for a,n,b in zip(low,p,high))or tuple(p)in result):raise RuntimeError('Distinct block observations inside original bounds required')
            result[tuple(p)]=row['state']
        return result
    original=rows(before)
    if any(p in original or not all(a<=n<=b for a,n,b in zip(low,p,high))for p in targets):raise RuntimeError('Every original target must have been witnessed air')
    before_stock=dict(inventory_counts(before));last=before.get('time');previous=None;summary=None
    for frame in frames:
        current=rows(frame);printer=frame.get('professional_printer')or{};job=frame.get('build_job')or{};proposal=printer.get('last_proposal')or{}
        if (type(last)is not int or type(frame.get('time'))is not int or frame['time']<=last
                or job.get('active')is not False or job.get('loading')is not False or job.get('outcome')!='printer_error'
                or job.get('queue_settled')is not True or job.get('placement_key')!=key
                or printer.get('owned')is not False or printer.get('enabled')is not False
                or printer.get('waiting_for_server')is not False or printer.get('travel_pending')!=0
                or printer.get('failure')!=FAILURE or printer.get('fast_proposals')!=0
                or type(printer.get('complex_proposals'))is not int or printer['complex_proposals']<1
                or printer.get('server_confirmed')!=printer['complex_proposals']):raise RuntimeError('Original queue has unsettled or unacknowledged input')
        done=sorted(p for p in targets if current.get(p)==DOUBLE);partial=sorted(p for p in targets if current.get(p)in HALVES);missing=sorted(p for p in targets if p not in current)
        if not done or len(partial)!=1 or len(done)+len(partial)+len(missing)!=len(targets)or job.get('new_blocks')!=len(done):raise RuntimeError('Exact verified prefix and one intermediate half required')
        target=proposal.get('target');expected_target=', '.join(map(str,partial[0]));actual=current[partial[0]]
        if (target!=expected_target or proposal.get('interaction_seen')is not True or proposal.get('server_update_seen')is not True
                or proposal.get('interaction_matches_proposal')is not True or proposal.get('expected')!=actual
                or proposal.get('server_update_state')!=actual or proposal.get('ack_actual')!=actual
                or proposal.get('ack_final')is not False or proposal.get('final_target')!=DOUBLE):raise RuntimeError('Last half placement lacks its original individual ACK')
        changes={p for p in original.keys()|current.keys()if original.get(p)!=current.get(p)}
        if changes!=set(done+partial):raise RuntimeError('A surrounding block changed or material balance differs')
        cost=2*len(done)+len(partial)
        if before_stock.get('minecraft:cobblestone_slab',0)<cost:raise RuntimeError('Original slab stock cannot fund the observed prefix')
        stock=deepcopy(before_stock);stock['minecraft:cobblestone_slab']-=cost;stock={k:v for k,v in stock.items()if v}
        if stock!=dict(inventory_counts(frame)):raise RuntimeError('Whole inventory does not exactly conserve the observed slab prefix')
        now=(done,partial,missing,printer,job.get('session'))
        if previous is not None and now!=previous:raise RuntimeError('Stopped original evidence changed between observations')
        previous=now;last=frame['time'];summary={'completed_targets':[list(p)for p in done],'partial_targets':[list(p)for p in partial],'never_attempted_air_targets':[list(p)for p in missing],'slab_debit':cost}
    return {'schema':1,'classification':'settled_printer_failure_after_individually_acknowledged_half',
        'world_session':world,'task_session':owner['job_session'],'placement_key':key,'original_mask_complete':False,
        'outstanding_native_input':False,'original_requests_replayed':False,'old_world_labels_rebound':False,
        'releasable_reservations':deepcopy(mask),'host_hashes':deepcopy(HOST_HASHES),**summary}
