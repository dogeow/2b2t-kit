"""Admission for an authorized, stable unowned storage close used only to recover food/health."""
import math
SAFE={'ShulkerBoxScreen':'ShulkerBoxMenu','ContainerScreen':'ChestMenu','InventoryScreen':'InventoryMenu'}

def signature(state):
    menu=state.get('menu')or{}
    return (state.get('world_session'),state.get('control_revision'),state.get('screen'),menu.get('id'),menu.get('type'),
        menu.get('slots') or [],menu.get('cursor') or {})

def may_recover_ui(before,current,idle_seconds,*,authorized=False,hardware_idle=None):
    try:
        if (authorized is not True or type(idle_seconds)not in(int,float)or not math.isfinite(idle_seconds)or idle_seconds<30
                or signature(before)!=signature(current)or not isinstance(current.get('world_session'),str)or not current['world_session']
                or current.get('connected')is not True or current.get('manual_movement')is not False
                or current.get('supervision_lease')or current.get('safety_hold',{}).get('active')or current.get('health_recovery_hold')
                or current.get('guard_busy')or current.get('under_water')or current.get('player_dead')
                or current.get('health',0)<19 or current['health']<before.get('health',20)
                or current.get('recent_hurt_at')!=before.get('recent_hurt_at')
                or current.get('screen')not in SAFE or SAFE[current['screen']]!=(current.get('menu')or{}).get('type')
                or(current.get('menu')or{}).get('cursor',{}).get('count')!=0
                or any(current.get(k)for k in ['navigating','chopping','printing','borer_active','fisher_active','planter_active','feeder_active'])
                or(current.get('material_task')or{}).get('occupied')):return False
        if(current.get('menu')or{}).get('type')=='InventoryMenu':
            slots=current['menu'].get('slots')or[]
            if len(slots)<5 or any(slots[i].get('count')!=0 for i in range(1,5)):return False
        if current.get('window_active')is not False and not(type(hardware_idle)in(int,float)and math.isfinite(hardware_idle)and hardware_idle>=30):return False
        a,b=before.get('pos'),current.get('pos')
        return bool(isinstance(a,list)and isinstance(b,list)and len(a)==len(b)==3
            and all(type(v)in(int,float)and math.isfinite(v)for v in a+b)and math.dist(a,b)<=.12)
    except(KeyError,TypeError,ValueError):return False


def close_stable_storage(root,out,server,dimension='minecraft:overworld',*,observe=None,clock=None,sleep=None,hardware=None,client_type=None):
    """Close one explicitly authorized, unchanged storage screen without taking items."""
    import time
    from pathlib import Path
    from live_snapshot import read_fresh
    from manual_idle_resume import hardware_idle_seconds
    from material_client import Client
    observe=observe or (lambda:read_fresh(Path(root)))
    clock=clock or time.monotonic;sleep=sleep or time.sleep;hardware=hardware or hardware_idle_seconds
    client_type=client_type or Client
    before=observe()
    if before.get('screen') not in ('ContainerScreen','ShulkerBoxScreen'):return False
    start=clock()
    while clock()-start<30:
        sleep(.25);current=observe()
        if not may_recover_ui(before,current,30,authorized=True,hardware_idle=hardware()):return False
    current=observe();elapsed=clock()-start;idle=hardware()
    if not may_recover_ui(before,current,elapsed,authorized=True,hardware_idle=idle):return False
    client=client_type(root,out,server,dimension=dimension,idle_storage_proof={'before':before,'idle_seconds':elapsed,'hardware_idle':idle})
    result=client.checked('close_menu');after=observe()
    if result.get('phase')!='done' or after.get('world_session')!=before.get('world_session') or after.get('screen'):
        raise RuntimeError('Storage close not confirmed; preserve the original request')
    return True
