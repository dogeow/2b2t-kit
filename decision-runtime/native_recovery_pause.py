"""Recognize only Kit's explicit bounded residual-fire pause, never guess from health."""
import math


def waiting_for_residual_fire(state):
    pause=state.get('residual_fire_wait')or{}
    health=state.get('health')
    return (state.get('safe_residual_fire_wait_protocol')==1 and pause.get('active')is True
        and pause.get('phase')in ('waiting_for_fire','recovering')
        and state.get('connected')is True and state.get('guard_armed')is True
        and state.get('guard_pve_only')is True and not state.get('screen')
        and state.get('manual_movement')is False and not state.get('safety_hold',{}).get('active')
        and type(health)in (int,float)and math.isfinite(health)and health>=18)
