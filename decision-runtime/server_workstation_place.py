"""Place a prepared lectern through one bounded, server-confirmed printer mask."""
import time
from material_plan import inventory_counts
from terminal_confirmation import verified

def place_lectern(builder,position,acceptable):
    item='minecraft:lectern';state=builder.check()
    if state.get('professional_printer',{}).get('enabled')or state.get('projection_batch',{}).get('active'):
        raise RuntimeError('Finish the original printer scope before placing another workstation')
    transactions=builder.book.setdefault('verified_workstation_placements',[])
    if any(v.get('pending')for v in transactions):raise RuntimeError('Original workstation placement remains pending')
    model=builder.n('projection_model')['projection_model'];rows=model.get('expected')or[]
    matches=[r for r in rows if r.get('pos')==position and r.get('item')==item and r.get('state')in acceptable]
    key=model.get('placement_key')
    if(model.get('model_schema')!=1 or not model.get('loaded_chunks_verified')or not model.get('loaded_server_chunks_verified')
            or len(matches)!=1 or not isinstance(key,str)or not key):
        raise RuntimeError('Prepare the exact lectern projection before placement; generic interaction is not a fallback')
    expected=matches[0]['state'];before=inventory_counts(builder.check())[item]
    if before<1:raise RuntimeError('One real carried lectern is required')
    from public_lectern_access import approach,restore
    public_access=approach(builder,position,expected)
    transaction={'pending':True,'position':position,'expected':expected,'placement_key':key,'material_before':before}
    transactions.append(transaction);builder.save();builder.n('select_item',item=item)
    builder.n('projection_batch_set',placement_key=key,positions=[position])
    from guarded_workstation_print import print_once
    reply=print_once(builder,key,position,before);transaction['request']=reply.get('id');builder.save()
    if(not verified('professional_print',reply,builder.q.world,reply.get('id'),{})or reply.get('phase')!='done'
            or reply.get('placement_key')!=key or reply.get('bounded_targets')!=[position]or reply.get('bounded_target_count')!=1):
        raise RuntimeError('Exact workstation server acknowledgement missing; retain the original mask and receipt')
    times=[];deadline=time.monotonic()+8
    while len(times)<2:
        frame,cells=builder.scan(position,position);current=builder.check()
        if(cells.get(tuple(position),{}).get('state')==expected and inventory_counts(current)[item]==before-1
                and(not times or current['time']>times[-1])):times.append(current['time'])
        if time.monotonic()>=deadline:raise RuntimeError('Server-confirmed workstation still lacks conserved fresh physical frames')
        time.sleep(.1)
    builder.n('projection_batch_clear',placement_key=key)
    transaction.update(pending=False,server_confirmed=True,times=times)
    builder.book.setdefault('placed',[]).append({'pos':position,'item':item,'expected_state':expected,
        'acceptable_states':sorted(acceptable),'request':reply['id'],'times':times,'material_before':before,
        'server_confirmed':True,'printer_proposal':reply.get('professional_printer',{}).get('last_proposal')})
    builder.save();restore(builder,public_access);return reply
