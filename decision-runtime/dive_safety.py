"""Preflight for bounded shallow-seafloor gravel dives using Kit 1.9.73 state."""

from dive_gear_plan import enchantments


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
            and state.get('air_supply', 0) < 240):
        return 'Restore air before starting the dive'
    return None


def must_surface(state):
    return (not state.get('connected') or state.get('health', 0) < 18
            or state.get('air_supply', 0) < 150 and not (
                state.get('water_breathing_effect') or state.get('conduit_power_effect'))
            or state.get('manual_movement') or state.get('screen'))
