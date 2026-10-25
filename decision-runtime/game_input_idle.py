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


def may_reacquire_without_ui_input(state,policy,game_idle):
    threshold=policy.get('idle_seconds')
    return (policy.get('authorized')is True and type(threshold)in(int,float)and 30<=threshold<=600
        and type(game_idle)in(int,float)and math.isfinite(game_idle)and game_idle>=threshold
        and state.get('connected')is True and state.get('health')==20 and state.get('manual_movement')is False
        and not state.get('screen')and not state.get('supervision_lease')and not state.get('guard_busy')
        and not state.get('health_recovery_hold')and not state.get('safety_hold',{}).get('active')
        and not any(word in state.get('detail','')for word in ('停止全部','紧急停止')))
