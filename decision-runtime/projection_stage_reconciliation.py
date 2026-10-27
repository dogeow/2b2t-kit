"""Conserve a stopped projection stage; observations never authorize a replay."""
from collections import Counter
from material_plan import inventory_counts

ERROR='Same native printer stage made no new progress; retain current evidence'
INCOMPLETE='Village stage is physically incomplete'

def transient_wire(expected,actual):
    """Recognize only neighbor-derived wire connections, never power or a different block."""
    from projection_completion import block_state
    try:
        wanted,wp=block_state(expected);found,ap=block_state(actual)
    except (ValueError,TypeError):return False
    directions={'north','south','east','west'}
    return (wanted==found=='minecraft:redstone_wire' and set(wp)==set(ap)
            and directions<=set(wp) and all(wp[k]==ap[k]for k in wp if k not in directions))

def preview(command,error,stage,model,state,last,world,task):
    job=state.get('build_job')or{};printer=state.get('professional_printer')or{}
    if(command.get('action')!='build_village_stage' or error.get('error')not in (ERROR,INCOMPLETE)
       or error.get('type')!='RuntimeError' or 'native_inflight'not in error or error['native_inflight']is not None
       or 'unconfirmed_native_request'not in error or error['unconfirmed_native_request']is not None
       or error.get('last_request')!=state.get('last_request')
       or stage.get('world_session')!=world or stage.get('complete')is not False
       or not stage.get('passes') or job.get('active')is not False or job.get('queue_settled')is not True
       or job.get('outcome')=='manual_stop' or printer.get('enabled')is not False or printer.get('owned')is not False
       or printer.get('waiting_for_server')is not False
       or stage.get('placement_key')!=model.get('placement_key') or stage['placement_key']!=job.get('placement_key')
       or last.get('request_id')!=state.get('last_request') or last.get('op')!='projection_audit'
       or last.get('world_session')!=world or last.get('params',{}).get('task_session')!=task
       or last.get('revision_after')!=state.get('control_revision') or last.get('position_after')!=state.get('pos')
       or state.get('screen') or state.get('manual_movement')is not False or state.get('health')!=20
       or state.get('navigating') or state.get('native_material_busy') or state.get('pending_scan')):
        raise ValueError('No exact stopped projection stage')
    audit=stage['passes'][-1];rows=model.get('expected',[])
    pending=printer.get('travel_pending',0)
    if type(pending)is not int or pending not in (0,1):
        raise ValueError('Unbounded pending printer scope')
    if pending:
        proposal=printer.get('last_proposal')or{}
        try:target=[int(v.strip())for v in proposal['target'].split(',')]
        except(KeyError,ValueError,AttributeError):raise ValueError('Pending printer target unavailable')
        if target not in [r['pos']for r in rows] or proposal.get('interaction_matches_proposal')is not True:
            raise ValueError('Pending printer target is outside the observed stage')
    if(not rows or audit.get('total')!=len(rows) or not audit.get('loaded_server_chunks_verified')
       or audit.get('placement_key')!=stage['placement_key'] or audit.get('matched')!=job.get('matched')
       or len(audit.get('mismatches',[]))!=len(rows)-audit['matched']
       or any(r.get('kind')!='missing'and not(r.get('kind')=='state_only'
                 and transient_wire(r.get('expected'),r.get('actual')))for r in audit['mismatches'])):
        raise ValueError('Partial stage needs complete audit')
    return model['bounds']

def reconcile(stage,model,frame,state):
    prediction=frame.get('scan_predictions')or{};bounds=model['bounds'];volume=1
    for lo,hi in zip(bounds['min'],bounds['max']):volume*=hi-lo+1
    if(frame.get('world_session')!=stage['world_session'] or frame.get('scan_cells_read')!=volume
       or frame.get('scan_total_cells')!=volume or frame.get('unloaded_chunks')
       or prediction.get('complete')is not True or prediction.get('pending_count')!=0
       or prediction.get('pending_positions')!=[]):
        raise ValueError('Pending predictions or incomplete world observation')
    actual={tuple(r['pos']):r['state']for r in frame['blocks']};initial_missing={tuple(r['pos'])for r in stage['before']['mismatches']}
    expected=Counter(stage['inventory_before']);matched=0;missing=[];wire_topology=[]
    for row in model['expected']:
        pos=tuple(row['pos'])
        if actual.get(pos)==row['state']:
            matched+=1
            if pos in initial_missing:expected[row['item']]-=1
        elif transient_wire(row['state'],actual.get(pos)):
            if row['item']!='minecraft:redstone':raise ValueError('Wire material identity changed')
            if pos in initial_missing:expected[row['item']]-=1
            wire_topology.append(dict(pos=row['pos'],expected=row['state'],actual=actual[pos]))
        elif pos not in actual:missing.append(row['pos'])
        else:raise ValueError('Unexpected replacement in projection stage')
    if matched<stage['passes'][-1]['matched'] or +expected!=inventory_counts(state):
        raise ValueError('Partial stage blocks and material debit disagree')
    return dict(matched=matched,total=len(model['expected']),missing=missing,inventory_after=dict(+expected),
                pending_wire_topology=wire_topology,physical_placements=matched+len(wire_topology),
                final_topology_verified=not wire_topology,replayed=False)
