"""Wait only for an unqueued containment refusal; never repeat a native print."""
import json,time
from pathlib import Path
from material_plan import inventory_counts

PREFIX='Contain current grown or displaced villagers before installing a workstation: '

def print_once(builder,key,target,before,*,timeout=30):
    if type(timeout)not in(int,float)or not 0<=timeout<=30:raise ValueError('Bounded containment observation required')
    out=getattr(builder.q,'out',None);path=Path(out)/'command.json'if out is not None else None
    baseline=path.read_bytes()if path is not None else None
    deadline=time.monotonic()+timeout
    while True:
        try:return builder.n('professional_print',seconds=20)
        except RuntimeError as error:
            if not str(error).startswith(PREFIX)or baseline is None:raise
            # The local assignment check runs before dispatch. Its last command
            # must still be the exact successful mask setter, byte-for-byte.
            if path.read_bytes()!=baseline or (Path(out)/'control/unconfirmed-native-request.json').exists():raise
            command=json.loads(baseline);directory=Path(out)/command['id']
            if(command.get('action')!='native'or command.get('op')!='projection_batch_set'
               or command.get('params')!={'placement_key':key,'positions':[target]}
               or(directory/'error.json').exists()or not(directory/'result.json').exists()):raise
            reply=json.loads((directory/'result.json').read_text());state=builder.check();batch=state.get('projection_batch')or{}
            if(reply.get('phase')!='done'or reply.get('world_session')!=builder.q.world
               or state.get('world_session')!=builder.q.world or state.get('health')!=20
               or state.get('manual_movement')is not False
               or state.get('control_revision')!=reply.get('control_revision')
               or state.get('native_material_busy')or state.get('pending_scan')
               or batch.get('active')is not True or batch.get('placement_key')!=key
               or batch.get('count')!=1 or batch.get('task_session')!=builder.q.lease['job_session']
               or state.get('professional_printer',{}).get('enabled')is not False
               or inventory_counts(state)['minecraft:lectern']!=before):raise
            if time.monotonic()>=deadline:raise
            builder.book.setdefault('unissued_print_containment_waits',[]).append({'time':state.get('time'),'last_mask_command':command['id'],'reason':str(error),'no_print_dispatched':True});builder.save()
            time.sleep(.5)
