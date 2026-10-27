"""Current-player checks for Kit native stages, independent of external planners."""
from pathlib import Path
KIT=Path(__file__).resolve().parents[1]
STAGES=KIT/'work/native-stages'

def free_slots(state):
 return sum(not row.get('count')for row in state.get('inventory',[])if 0<=row.get('slot',99)<36)

def require_player(client):
 state=client.status();lease=state.get('supervision_lease')or{}
 if(state.get('connected')is not True or state.get('world_session')!=client.world
    or state.get('health')!=20 or state.get('manual_movement')or state.get('screen')
    or state.get('health_recovery_hold')or(state.get('safety_hold')or{}).get('active')
    or lease.get('job_session')!=client.task):
  raise RuntimeError('Native stage lost current healthy Kit owner')
 return state
