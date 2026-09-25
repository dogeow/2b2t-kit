"""Choose one ordinary hotbar meal before a guarded material dive."""

PREFERRED = (
    'minecraft:cooked_porkchop',
    'minecraft:cooked_beef',
    'minecraft:cooked_chicken',
    'minecraft:bread',
)


def guarded_hotbar_meal(state):
    if (not state.get('connected') or state.get('health', 0) < 19
            or state.get('air_supply', 0) < 295 or state.get('under_water')
            or state.get('manual_movement') or state.get('screen')
            or not state.get('guard_armed') or state.get('food', 0) >= 18):
        return None
    hotbar = {item['item'] for item in state.get('inventory', [])
              if item.get('slot', 100) < 9 and item.get('count', 0) > 0}
    return next((item for item in PREFERRED if item in hotbar), None)
