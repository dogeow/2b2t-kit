"""Observe Minecraft inactivity without treating typing in other apps as game input.

This grants no UI-key or gameplay authority. Foreground-changing AppleScript
still needs its separate whole-desktop inactivity checks.
"""
import math

class GameInputIdle:
    def __init__(self):self.world=None;self.last_activity=None;self.last_now=None
    def observe(self,state,hardware_idle_seconds,now):
        if type(now)not in(int,float)or not math.isfinite(now)or(self.last_now is not None and now<self.last_now):raise ValueError('Monotonic observation time required')
        self.last_now=now
        if(state.get('connected')is not True or not isinstance(state.get('world_session'),str)
                or not state['world_session']or type(state.get('window_active'))is not bool
                or type(state.get('manual_movement'))is not bool):
            self.world=None;self.last_activity=None;return None
        if self.world!=state['world_session']:
            self.world=state['world_session'];self.last_activity=now
        if state['manual_movement']:
            self.last_activity=now;return 0.
        if state['window_active']:
            if (type(hardware_idle_seconds)not in(int,float)or not math.isfinite(hardware_idle_seconds)or hardware_idle_seconds<0):
                self.last_activity=now;return None
            self.last_activity=max(self.last_activity,now-hardware_idle_seconds)
        # When another app has focus, its keystrokes do not reset this clock.
        return max(0.,now-self.last_activity)


def _idle_owner_free(state,policy,game_idle):
    threshold=policy.get('idle_seconds')
    return (policy.get('authorized')is True and type(threshold)in(int,float)and 30<=threshold<=600
        and type(game_idle)in(int,float)and math.isfinite(game_idle)and game_idle>=threshold
        and state.get('connected')is True and state.get('manual_movement')is False
        and not state.get('screen')and not state.get('supervision_lease')and not state.get('guard_busy')
        and not any(state.get(k)for k in ('borer_active','chopping','navigating','printing','native_material_busy','pending_scan','material_mining_cleanup_pending'))
        and not (state.get('build_job')or{}).get('active')
        and not (state.get('professional_printer')or{}).get('enabled')
        and not (state.get('material_task')or{}).get('occupied')
        and not state.get('health_recovery_hold')and not state.get('safety_hold',{}).get('active')
        and not any(word in state.get('detail','')for word in ('停止全部','紧急停止')))


def may_reacquire_without_ui_input(state,policy,game_idle):
    return state.get('health')==20 and _idle_owner_free(state,policy,game_idle)


def may_start_food_recovery(state,policy,game_idle):
    """Only ordinary food recovery may precede the unchanged full-health work gate."""
    health=state.get('health');food=state.get('food')
    return (type(health)in(int,float)and math.isfinite(health)and 18<=health<20
        and type(food)is int and 0<=food<18
        and state.get('dimension')=='minecraft:overworld'
        and not(state.get('guard_food')or{}).get('eating')
        and any(row.get('slot',99)<9 and row.get('count',0)>0
                and row.get('item')in ('minecraft:cooked_beef','minecraft:cooked_porkchop','minecraft:cooked_chicken','minecraft:cooked_mutton','minecraft:bread')
                for row in state.get('inventory',[]))
        and _idle_owner_free(state,policy,game_idle))
