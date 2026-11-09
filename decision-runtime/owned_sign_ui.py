"""Close only a new editor opened by this controller's one-cell printer batch."""
import math,subprocess,time
from pathlib import Path
from manual_idle_resume import hardware_idle_seconds
from material_plan import inventory_counts
from kit_runtime.journal import write_json


def may_close(state,scope,hardware_idle,elapsed):
    try:
        if not isinstance(scope,dict)or not isinstance(state,dict):return False
        lease=state.get('supervision_lease')or{};printer=state.get('professional_printer')or{}
        batch=state.get('projection_batch')or{};proposal=printer.get('last_proposal')or{};menu=state.get('menu')or{}
        hp=state.get('health');food=state.get('food');revision=state.get('control_revision')
        if(type(hardware_idle)not in(int,float)or not math.isfinite(hardware_idle)
           or type(elapsed)not in(int,float)or not math.isfinite(elapsed)or elapsed<0
           or hardware_idle<max(30,elapsed+1)):return False
        # The idle clock must predate the print start. Later typing is never discarded.
        if(state.get('connected')is not True or state.get('world_session')!=scope['world']
           or state.get('manual_movement')is not False or state.get('screen')!='SignEditScreen'
           or state.get('guard_armed')is not True or state.get('guard_pve_only')is not True
           or state.get('guard_busy')or state.get('safety_hold',{}).get('active')
           or type(hp)not in(int,float)or not math.isfinite(hp)or hp<19
           or type(food)is not int or food<18
           or type(revision)is not int or revision!=scope['start_revision']+1
           or lease.get('kind')!='materials'or lease.get('job_session')!=scope['task']
           or lease.get('world_session')!=scope['world']or lease.get('revision')!=revision
           or menu.get('type')!='InventoryMenu'or menu.get('id')!=0
           or menu.get('cursor',{}).get('count')!=0):return False
        slots=menu.get('slots')or[]
        if len(slots)<5 or any(slots[i].get('count')!=0 for i in range(5)):return False
        target=', '.join(map(str,scope['target']))
        return bool(printer.get('owned')is True and batch.get('active')is True and batch.get('count')==1
          and batch.get('placement_key')==scope['key']and batch.get('task_session')==scope['task']
          and proposal.get('target')==target and proposal.get('final_target')==scope['expected']
          and proposal.get('hand')==scope['item']and proposal.get('interaction_seen')is True
          and type(scope['before_count'])is int and scope['before_count']>0
          and inventory_counts(state).get(scope['item'],0)==scope['before_count']-1)
    except(KeyError,TypeError,ValueError,AttributeError):return False


def maybe_close(client,state):
    scope=getattr(client,'owned_sign_scope',None)
    if not scope or getattr(client,'owned_sign_close_attempted',False)or state.get('screen')!='SignEditScreen':return False
    now=time.monotonic()
    if now<getattr(client,'owned_sign_next_check',0):return False
    client.owned_sign_next_check=now+1
    idle=hardware_idle_seconds()
    if not may_close(state,scope,idle,now-scope['started']):return False
    client.owned_sign_close_attempted=True
    receipt={'world_session':scope['world'],'task_session':scope['task'],'target':scope['target'],
      'hardware_idle_seconds':idle,'seconds_since_print_start':now-scope['started'],'attempt_reserved':True,
      'requires_fresh_native_observation':True,'no_placement_replay':True}
    path=client.out/'owned-sign-ui-close.json';write_json(path,receipt)
    try:
        game=Path(client.root).parents[2];pids=set(subprocess.check_output(['lsof','-t',str(game/'logs/latest.log')],text=True).split())
        if len(pids)!=1:raise RuntimeError('Game process identity is ambiguous')
        pid=int(next(iter(pids)))
        script='tell application "System Events"\n set gameProcess to first application process whose unix id is %d\n if name of gameProcess does not contain "java" then error "Expected existing Java game process"\n set frontmost of gameProcess to true\n delay 0.2\n set idleReport to do shell script "/usr/sbin/ioreg -c IOHIDSystem -r | /usr/bin/awk \'/HIDIdleTime/ {print $NF; exit}\'"\n if (idleReport as real) < 30000000000 then error "Human input resumed; Escape was not sent"\n tell gameProcess to key code 53\nend tell\n'
        r=subprocess.run(['/usr/bin/osascript','-'],input=script%pid,text=True,capture_output=True,timeout=6,check=True)
        receipt['escape_sent']=True;write_json(path,receipt);print('OWNED_SIGN_ESCAPE_SENT',scope['target'],flush=True);return True
    except(Exception)as e:
        receipt.update(escape_sent=False,error=str(e));write_json(path,receipt)
        print('OWNED_SIGN_UI_NEEDS_MANUAL_CLOSE',str(e),flush=True);return False
