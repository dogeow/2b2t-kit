"""Publish only the current SDK-owned container window for external observers."""
from pathlib import Path

def owned_menu_result(c,result):
    """Publish the SDK's explicit window ownership, absent from raw host status."""
    from kit_runtime.journal import write_json
    final=c.status()
    if not isinstance(final,dict):return result
    menu=final.get('menu')or{};lease=final.get('supervision_lease')or{}
    if(type(menu.get('id'))is not int or menu['id']<=0 or menu['id']!=getattr(c,'owned_material_menu',None)):
        if isinstance(getattr(c,'out',None),(str,Path)):(Path(c.out).parent/'owned-material-menu.json').unlink(missing_ok=True)
        return result
    certificate={'type':menu['type'],'id':menu['id'],'world_session':c.world,'task_session':c.task,
                 'lease_id':lease.get('id'),'control_revision':final['control_revision']}
    if isinstance(getattr(c,'out',None),(str,Path)):
        write_json(Path(c.out).parent/'owned-material-menu.json',certificate)
    return {**result,'owned_menu':certificate}
