"""Scoped food and clear-column recovery. No harvesting, unlock, or reconnect."""
import math
import time
from pathlib import Path
from live_snapshot import read_fresh
from material_client import MaterialClient
from job_progress import JobProgress
from safety_interlock import require_unlocked

FOOD=('minecraft:cooked_beef','minecraft:cooked_porkchop','minecraft:baked_potato','minecraft:cooked_mutton','minecraft:cooked_chicken','minecraft:bread')
def recover(game_dir,out):
    root=Path(game_dir)/'config/twob2tkit/automation';initial=read_fresh(root);require_unlocked(root,initial)
    if (not initial.get('connected') or initial.get('manual_movement') or initial.get('screen')
            or initial.get('dimension')!='minecraft:overworld' or initial.get('under_water')
            or initial.get('health',0)<14):raise RuntimeError('Dry idle recovery requires at least seven hearts and an unlocked live world')
    target=[initial['pos'][0],min(320,max(100,initial['pos'][1]+32)),initial['pos'][2]]
    c=MaterialClient(root,out,server=initial['server'],remote_finish='guard',park_target=target,
                     recovery_only=True,record_experience=False)
    c.job_progress=JobProgress(root,c.world,c.task,c.rev,'安全恢复',1)
    try:
        state=c.status()
        if state.get('food',0)<20:
            carried={v['item']:v['count'] for v in state['inventory'] if v['count']>0}
            item=next((v for v in FOOD if carried.get(v)),None)
            if item is None:raise RuntimeError('No confirmed carried cooked food; no external gathering started')
            c.set_progress(phase='进食');c.checked('select_item',item=item);c.checked('use_item',item=item,seconds=6)
            if c.status().get('food',0)<18:raise RuntimeError('Food use did not restore work reserve; no duplicate use')
        # MaterialClient verifies the complete actual dry body column first.
        c.set_progress(phase='原地升高');c._finish_vertical(c.status())
        c.set_progress(phase='等待回血');deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            state=c.status()
            if state.get('health',0)<14:raise RuntimeError('Critical health; native emergency protection retains priority')
            if state['health']==20 and state['food']>=18:
                c.set_progress(done=1,phase='已恢复')
                return {'phase':'done','health':state['health'],'food':state['food'],'pos':state['pos'],
                        'proof_scope':'current_owned_native_status_not_future_survival_guarantee'}
            time.sleep(.25)
        return {'phase':'waiting','detail':'Recovery reserve not reached; no ordinary work started'}
    finally:c.finish()
