"""One reversible hotbar correction after a known completed item selection."""
from material_plan import inventory_counts

def correction_slot(reply,state,item):
    lease=state.get('supervision_lease')or{}
    if (reply.get('phase')!='done' or reply.get('id')!=state.get('last_request')
            or reply.get('world_session')!=state.get('world_session')
            or reply.get('control_revision')!=state.get('control_revision')
            or reply.get('supervision_lease')!=lease or lease.get('kind')!='materials'
            or not lease.get('job_session') or state.get('health')!=20
            or state.get('manual_movement')is not False or state.get('screen')
            or state.get('navigating') or state.get('native_material_busy')
            or inventory_counts(reply)!=inventory_counts(state)
            or reply.get('pos')!=state.get('pos')):
        return None
    menu=state.get('menu')or{}
    if menu.get('id')!=0 or menu.get('cursor',{}).get('item')!='minecraft:air':return None
    rows={v['slot']:v for v in reply.get('inventory',[])if type(v.get('slot'))is int}
    for row in state.get('inventory',[]):
        slot=row.get('slot')
        if(type(slot)is int and 0<=slot<=8 and row.get('item')==item and row.get('count',0)>0
                and rows.get(slot)==row):
            return slot
    return None
