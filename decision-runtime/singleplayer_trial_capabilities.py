"""Small, factual capability descriptions for Clef's current trial choices.

This is the registered trial macro subset, not an inventory of all Kit/Meteor
menus. The caller's native candidate builder supplies reachability/plan checks;
this module applies cheap state checks and never supplies action parameters.
"""
from __future__ import annotations

import json
import math


PROTOCOL = 1
MAX_AVAILABLE = 10
DEFAULT_MAX_BYTES = 1800

# Primitive names come from TrialBridge and Runner's normal interactions.
# Preconditions here describe only checks actually made by candidates(), not a
# claim that every later interaction will succeed. Each primitive rechecks live.
CATALOG = {
    'gather_starting_wood': ('采集附近已观察到的原木', 'get logs', 'wood deficit; reachable tree',
                             'walk_path,mine_block', 'log inventory gain'),
    'craft_wooden_tools': ('用背包木材制作工作台和木镐', 'make wood tools', 'wood; safe work stance; no pickaxe',
                           'craft_recipe,interact', 'crafted items in inventory'),
    'gather_stone': ('用现有镐采集附近石料', 'get cobblestone', 'pickaxe; stone deficit; reachable stone',
                     'walk_path,mine_block', 'cobblestone inventory gain'),
    'craft_stone_tools': ('用已有圆石制作石工具和熔炉', 'make stone tools', 'pickaxe; enough cobblestone; safe station',
                          'craft_recipe,interact', 'tools/furnace in inventory'),
    'gather_food': ('获取附近被动动物掉落物并烹饪', 'get cooked food', 'stone axe; animal; furnace; food deficit',
                    'attack_passive,slot_click', 'edible inventory gain'),
    'eat_carried_food': ('食用背包已有食物恢复饥饿值', 'eat carried food', 'hunger<16; edible stock',
                         'select_item,use_item', 'hunger increases; food consumed'),
    'gather_shelter_material': ('按本世界庇护方案采集缺少的泥土', 'get shelter dirt', 'camp plan; tools; food; dirt deficit',
                               'walk_path,mine_block', 'dirt inventory gain'),
    'build_shelter': ('按已观察方案建造并复核小庇护所', 'build shelter', 'camp plan; tools; food; dirt stock',
                      'craft_recipe,interact,scan', 'all planned blocks/door scanned'),
    'prepare_iron_equipment': ('采集露天铁矿、熔炼并穿戴铁装备', 'prepare iron gear', 'completed camp; tools; food; iron/ore',
                               'mine_block,slot_click,craft_recipe', 'iron tools/armor in inventory/equipment'),
    'explore_nearby': ('沿扫描过的安全步行路线探索附近', 'explore nearby', 'new scanned safe path; bounded route',
                       'walk_path,scan', 'current position near route end'),
    'recover_after_death': ('通过游戏正常重生并重新观察环境', 'normal respawn', 'native player death; registered trial',
                            'trial_respawn', 'alive native state; fresh observation'),
    'wait': ('等待新证据或补齐原生能力', 'wait', 'no action required',
             'none', 'no gameplay action dispatched'),
}

PROGRESSION_GAPS = (
    'nether_portal_construction', 'blaze_rod_collection', 'ender_pearl_collection',
    'stronghold_location_and_portal', 'end_crystal_and_dragon_combat',
)
MENUS = frozenset({'', 'InventoryScreen', 'CraftingScreen', 'FurnaceScreen',
                   'BlastFurnaceScreen', 'SmokerScreen'})
FOOD = frozenset({'cooked_beef', 'cooked_porkchop', 'cooked_mutton',
                  'cooked_chicken', 'bread', 'apple', 'baked_potato',
                  'cooked_cod', 'cooked_salmon'})


def _inventory(state):
    raw = state.get('inventory')
    if not isinstance(raw, list) or len(raw) > 128:
        return {}
    result = {}
    for stack in raw:
        if not isinstance(stack, dict):
            return {}
        item, count = stack.get('item'), stack.get('count')
        if not isinstance(item, str) or not item.startswith('minecraft:') or type(count) is not int or not 0 <= count <= 999:
            return {}
        name = item.removeprefix('minecraft:')
        result[name] = result.get(name, 0) + count
    return result


def _is_dead(state):
    health = state.get('health')
    return (state.get('player_dead') is True or
            (type(health) in (int, float) and math.isfinite(health) and health <= 0))


def _native_gate(state):
    if not isinstance(state, dict):
        return False
    identity = state.get('trial_identity')
    return (state.get('connected') is True and state.get('server') == 'singleplayer'
            and state.get('game_mode') == 'survival' and state.get('singleplayer_trial_protocol') == 1
            and isinstance(identity, dict) and identity.get('registered') is True
            and state.get('manual_movement') is not True
            and (state.get('game_paused') is not True or _is_dead(state))
            and (state.get('screen', '') in MENUS or (_is_dead(state) and state.get('screen') == 'DeathScreen')))


def _cheap_prerequisites(action, state):
    if action == 'wait':
        return True
    if action == 'recover_after_death':
        return _is_dead(state)
    if _is_dead(state) or state.get('dimension') != 'minecraft:overworld':
        return False
    inv = _inventory(state)
    pickaxe = any(inv.get(item, 0) > 0 for item in ('wooden_pickaxe', 'stone_pickaxe', 'iron_pickaxe'))
    if action == 'craft_wooden_tools':
        wood = sum(n for name, n in inv.items() if name.endswith('_log'))
        planks = sum(n for name, n in inv.items() if name.endswith('_planks'))
        return not pickaxe and (wood >= 4 or planks >= 12)
    if action == 'gather_stone':
        return pickaxe
    if action == 'craft_stone_tools':
        return pickaxe and inv.get('cobblestone', 0) >= 3
    if action == 'gather_food':
        return inv.get('stone_axe', 0) > 0
    if action == 'eat_carried_food':
        food = state.get('food')
        return (type(food) is int and 0 <= food < 16
                and any(inv.get(item, 0) > 0 for item in FOOD))
    if action in ('gather_shelter_material', 'build_shelter', 'prepare_iron_equipment'):
        return (inv.get('stone_pickaxe', 0) > 0 and inv.get('stone_axe', 0) > 0
                and sum(inv.get(item, 0) for item in FOOD) >= 4)
    return True  # Geometry/private camp details remain the native builder's checks.


def eligible_candidates(candidates, state):
    """A fixed-name subset; unknown/unavailable entries can never become actions."""
    if not _native_gate(state) or not isinstance(candidates, (dict, list, tuple)):
        return {}
    return {action: CATALOG[action][1] for action in candidates
            if isinstance(action, str) and action in CATALOG and _cheap_prerequisites(action, state)}


def capability_scene(candidates, state, *, max_bytes=DEFAULT_MAX_BYTES, max_available=MAX_AVAILABLE):
    """Build a bounded model scene. No source labels, coordinates or raw args leak.

    The budget bounds this field's JSON, not the entire inference context. With
    images, the caller should use a smaller budget and count the whole scene.
    Candidate omission for space does not authorise a different action.
    """
    if type(max_bytes) is not int or not 700 <= max_bytes <= 4096:
        raise ValueError('Capability scene byte budget must be 700..4096')
    if type(max_available) is not int or not 1 <= max_available <= MAX_AVAILABLE:
        raise ValueError('Available capability limit must be 1..10')
    allowed = eligible_candidates(candidates, state)
    result = {'protocol': PROTOCOL, 'scope': 'registered_trial_macros_only',
              'available': [], 'blocked': {name: 'unsupported' for name in PROGRESSION_GAPS},
              'checked_by': 'native_candidate_builder; skills recheck live',
              'omitted': len(allowed)}
    rejected = (len(candidates) - len(allowed)) if isinstance(candidates, (dict, list, tuple)) else 0
    if rejected:
        result['unavailable'] = {'count': rejected, 'status': 'needs_prerequisite_or_unregistered'}
    for action in allowed:
        _, purpose, preconditions, primitives, evidence = CATALOG[action]
        row = {'id': action, 'use': purpose, 'checked': preconditions,
               'via': primitives, 'verify': evidence}
        next_result = {**result, 'available': result['available'] + [row], 'omitted': result['omitted'] - 1}
        if len(next_result['available']) > max_available or len(json.dumps(next_result, separators=(',', ':')).encode()) > max_bytes:
            continue
        result = next_result
    return result


def capability_catalog():
    """Human-readable registry for docs/UI; never dump this into a model prompt."""
    return [{
        'id': action, 'description': values[0], 'checked_preconditions': values[2],
        'native_primitives': values[3].split(','), 'completion_evidence': values[4],
        'parameters_from': 'current_native_skill_not_model',
    } for action, values in CATALOG.items()]
