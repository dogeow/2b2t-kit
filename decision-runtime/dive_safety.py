"""Preflight for bounded shallow-seafloor gravel dives using Kit 1.9.73 state."""

import math
import time
from dive_gear_plan import enchantments


def native_air_budget(state):
    """Use a fresh, native-verified route budget; stale estimates never relax safety."""
    if state.get('air_budget_source') != 'observed':
        return None
    try:
        maximum = int(state.get('max_air_supply', 300))
        reserve = math.ceil(maximum / 10)
        return_floor = int(state['air_return_floor'])
        work_floor = int(state['air_work_floor'])
        valid_until = int(state['air_budget_valid_until'])
        return_y = float(state['air_return_y'])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if (not math.isfinite(return_y) or maximum <= 0
            or not reserve <= return_floor <= work_floor
            or valid_until <= time.time()*1000
            or state.get('air_return_active')):
        return None
    return return_floor, work_floor


def ascent_air_floor(state, surface_y=65, min_climb_blocks_per_second=2.5,
                     reserve_seconds=5):
    """Worst-case air for a vertical Flight return plus a full reserve."""
    native = native_air_budget(state)
    if native:
        return native[0]
    position=state.get('pos')
    if not position or len(position)!=3:
        return 280
    climb=max(0,surface_y-position[1])
    return max(240,math.ceil(20*(climb/min_climb_blocks_per_second+reserve_seconds)))


def work_air_floor(state):
    native = native_air_budget(state)
    return native[1] if native else max(260, ascent_air_floor(state)+20)


def pickup_air_floor(state):
    native = native_air_budget(state)
    if native:
        try:
            pickup = int(state['air_pickup_floor'])
            if native[0] <= pickup <= native[1]:
                return pickup
        except (KeyError, ValueError, TypeError):
            pass
        return native[1]
    return max(260, ascent_air_floor(state)+20)


def ready_for_gravel_dive(state):
    if state.get('bridge_version', 0) < 4:
        return 'Restart into Kit with oxygen and gear telemetry'
    if not state.get('connected') or state.get('dimension') != 'minecraft:overworld':
        return 'Expected live overworld session is absent'
    if state.get('screen') or state.get('manual_movement'):
        return 'Player interface or manual movement owns control'
    if state.get('health', 0) < 19 or state.get('food', 0) < 18:
        return 'Heal and eat before a dive'
    if not state.get('guard_armed') or not state.get('auto_log'):
        return 'PvE guard and automatic emergency logout are required'
    head = state.get('equipment', {}).get('head', {})
    boots = state.get('equipment', {}).get('feet', {})
    helmet_enchants = enchantments(head)
    boot_enchants = enchantments(boots)
    if helmet_enchants.get('aqua_affinity', 0) < 1 or helmet_enchants.get('respiration', 0) < 3:
        return 'Aqua Affinity and Respiration III helmet is required'
    if boot_enchants.get('depth_strider', 0) < 3:
        return 'Depth Strider III boots are required'
    shovel = next((item for item in state.get('inventory', [])
                   if item.get('slot', 100) == state.get('selected_slot')), {})
    if not shovel.get('item', '').endswith('_shovel') or shovel.get('durability', 0) < 100:
        return 'Select a shovel with at least 100 durability'
    if enchantments(shovel).get('fortune', 0):
        return 'Fortune shovel would turn gravel into flint'
    if (not state.get('water_breathing_effect') and not state.get('conduit_power_effect')
            and state.get('air_supply', 0) < work_air_floor(state)):
        return 'Restore air before starting the dive'
    return None


def must_surface(state):
    return (not state.get('connected') or state.get('health', 0) < 18
            or state.get('air_return_active', False)
            or state.get('air_supply', 0) < ascent_air_floor(state) and not (
                state.get('water_breathing_effect') or state.get('conduit_power_effect'))
            or state.get('manual_movement') or state.get('screen'))
