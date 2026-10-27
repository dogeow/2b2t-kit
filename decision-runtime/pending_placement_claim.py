"""Fence an unconfirmed placement's target and support without inventing its outcome."""
def guard(configuration,world,action,params):
    pending=[v for v in configuration.get('protected_pending_placement_targets',[])if v.get('world_session')==world and v.get('claim_not_cleared')is True]
    if not pending:return
    positions=set()
    for entry in pending:positions.update(tuple(entry[k])for k in('target','support'))
    if action=='native':
        op=params.get('op');native=params.get('params')or{}
        if op in('interact','mine_block','bucket_place')and tuple(native.get('pos')or[])in positions:raise RuntimeError('Project retains this unconfirmed placement; target and support remain fenced')
        if op=='projection_batch_set'and any(tuple(p)in positions for p in native.get('positions',[])):raise RuntimeError('Projection includes an unconfirmed placement target')
    elif action=='build_village_stage':
        import json
        with open(params['table'])as source:table=json.load(source)
        if any(tuple(v.get('pos')or[])in positions for v in table.get('expected',[])):raise RuntimeError('Build includes an unconfirmed placement target')
