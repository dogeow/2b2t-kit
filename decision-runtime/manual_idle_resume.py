"""Explicitly authorized idle UI release; no gameplay requests, logout or safety unlock."""
import json, math, re, subprocess, sys, time
from pathlib import Path

SAFE_SCREENS={'InventoryScreen':'InventoryMenu','PauseScreen':'InventoryMenu','ContainerScreen':'ChestMenu',
              'ShulkerBoxScreen':'ShulkerBoxMenu','MerchantScreen':'MerchantMenu',
              'CraftingScreen':'CraftingMenu','AnvilScreen':'AnvilMenu',
              'LoomScreen':'LoomMenu','StonecutterScreen':'StonecutterMenu',
              'FurnaceScreen':'FurnaceMenu','BlastFurnaceScreen':'BlastFurnaceMenu',
              'SmokerScreen':'SmokerMenu','BrewingStandScreen':'BrewingStandMenu'}
TRANSIENT={'InventoryMenu':range(1,5),'CraftingMenu':range(0,10),
           'MerchantMenu':range(0,3),'AnvilMenu':range(0,3),
           'LoomMenu':range(0,4),'StonecutterMenu':range(0,2)}

def may_close(state,policy,idle_seconds,world,task):
    """A key may only release a known empty-cursor interface after real hardware inactivity."""
    try:
        threshold=policy['idle_seconds'];menu=state.get('menu')or{};lease=state.get('supervision_lease')or{}
        if (policy.get('authorized')is not True or type(threshold)not in(int,float) or not 30<=threshold<=600
            or type(idle_seconds)not in(int,float) or not math.isfinite(idle_seconds) or idle_seconds<threshold
            or state.get('connected')is not True or state.get('health')!=20 or state.get('world_session')!=world
            or state.get('manual_movement')is not False or state.get('health_recovery_hold')
            or state.get('interface_paused')is not True or any((state.get('movement_keys')or{}).values())
            or state.get('safety_hold',{}).get('active') or state.get('guard_busy')
            or lease.get('kind')!='materials' or lease.get('world_session')!=world or lease.get('job_session')!=task
            or lease.get('revision')!=state.get('control_revision')
            or state.get('screen')not in SAFE_SCREENS or SAFE_SCREENS[state['screen']]!=menu.get('type')
            or menu.get('cursor',{}).get('count')!=0):
            return False
        slots=menu.get('slots')or[];required=TRANSIENT.get(menu['type'],())
        if any(i>=len(slots)or slots[i].get('count')!=0 for i in required):return False
        return True
    except(KeyError,TypeError,ValueError):return False

def hardware_idle_seconds():
    if sys.platform!='darwin':return None
    try:
        output=subprocess.run(['/usr/sbin/ioreg','-c','IOHIDSystem','-r'],capture_output=True,text=True,timeout=2,check=True).stdout
        values=re.findall(r'"HIDIdleTime"\s*=\s*(\d+)',output)
        return min(int(v)/1_000_000_000 for v in values) if values else None
    except(OSError,subprocess.SubprocessError,ValueError):return None

SCRIPT='''tell application "System Events"
 set candidates to {}
 repeat with p in (every application process whose name contains "java")
  try
   repeat with w in windows of p
    if (name of w as text) starts with "Minecraft" then
     set candidate to unix id of p
     if candidates does not contain candidate then set end of candidates to candidate
    end if
   end repeat
  end try
 end repeat
 if (count of candidates) is not 1 then error "Minecraft window identity is ambiguous"
 set gameProcess to first application process whose unix id is item 1 of candidates
 set frontmost of gameProcess to true
 delay 0.2
 tell gameProcess to key code 53
end tell'''

def maybe_release_interface(client,state):
    """Called by the existing sole owner while paused; policy is opt-in and task-local."""
    path=getattr(client,'manual_idle_resume_policy',None)
    if not path or time.monotonic()<getattr(client,'_manual_idle_next',0):return False
    client._manual_idle_next=time.monotonic()+2
    try:
        policy=json.loads(Path(path).read_text());idle=hardware_idle_seconds()
        if not may_close(state,policy,idle,client.world,client.task):return False
        fresh=client.raw();latest_idle=hardware_idle_seconds()
        if not may_close(fresh,policy,latest_idle,client.world,client.task):return False
        if fresh.get('screen')!=state.get('screen') or fresh.get('menu',{}).get('id')!=state.get('menu',{}).get('id'):return False
        # Reserve this attempt before input. A missing acknowledgement never authorizes another Esc.
        signature=(client.world,fresh['control_revision'],fresh['screen'],fresh['menu']['id'])
        if signature==getattr(client,'_manual_idle_attempt',None):return False
        client._manual_idle_attempt=signature
        subprocess.run(['/usr/bin/osascript','-e',SCRIPT],capture_output=True,text=True,timeout=5,check=True)
        from kit_runtime.journal import write_json
        write_json(client.out/'manual-idle-ui-release.json',{'world_session':client.world,'task_session':client.task,
                   'source_screen':fresh['screen'],'menu_id':fresh['menu']['id'],'hardware_idle_seconds':latest_idle,
                   'closed_by_authorized_escape':True,'gameplay_request_sent':False,'requires_fresh_native_observation':True})
        return True
    except(OSError,ValueError,TypeError,subprocess.SubprocessError):return False
