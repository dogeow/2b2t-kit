"""Health checks for explicitly requested stationary repairs, never general work."""
import math

def check(state,world,injuries):
 if(not injuries or any(not isinstance(uid,str)or type(h)not in(int,float)or not math.isfinite(h)or not 0<h<20 for uid,h in injuries.items())):
  raise ValueError('Exact positive known injury baselines required')
 lease=state.get('supervision_lease')or{}
 if(state.get('connected')is not True or state.get('world_session')!=world
    or state.get('health')!=20 or state.get('screen')!=''or state.get('manual_movement')is not False
    or state.get('health_recovery_hold')or(state.get('safety_hold')or{}).get('active')
    or state.get('guard_pve_only')is not True or lease.get('kind')!='materials'
    or lease.get('world_session')!=world or not lease.get('id')or not lease.get('job_session')):
  raise RuntimeError('Known-injury repair lost healthy owned PvE control')
 for actor in state.get('loaded_villagers',{}).get('villagers',[]):
  uid=actor.get('uuid');health=actor.get('health')
  if(type(health)not in(int,float)or not math.isfinite(health)or health>20 or health<injuries.get(uid,20)):
   raise RuntimeError('New resident injury during bounded station repair')
 return state
