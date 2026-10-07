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
    'collect_log_drops': ('沿扫描验证的路线正常步行拾取可见原木掉落物', 'pick up visible logs',
                         'visible log; path<=32; normal descent<=2 with dry floor/headroom/AABB checks',
                         'walk_path,walk,scan', 'log inventory gain'),
    'gather_starting_wood': ('调用 Kit 原生自动砍树完成单棵树、拾取和平台收尾', 'get logs',
                             'verified host; observed local species; natural-tree survey; support dirt; one native tree',
                             'scan_trees,chop', 'native cleanup and actual log inventory gain'),
    'craft_wooden_tools': ('用背包木材制作工作台和木镐', 'make wood tools', 'wood; safe local station stance; no pickaxe',
                           'slot_click,interact,scan', 'crafted items in inventory'),
    'gather_stone': ('用现有镐采集附近石料', 'get cobblestone', 'pickaxe; stone deficit; reachable stone',
                     'walk_path,mine_block', 'cobblestone inventory gain'),
    'craft_stone_tools': ('用已有圆石制作石工具和熔炉', 'make stone tools', 'pickaxe; cobblestone; reachable station or local table materials/footing',
                          'slot_click,interact,walk_path,scan', 'tools/furnace in inventory'),
    'gather_food': ('优先烹饪已有生食，缺生食且燃料备齐才获取动物食物', 'get cooked food', 'verified fuel; carried meat or axe/animal; furnace; food deficit',
                    'attack_passive,slot_click', 'edible inventory gain'),
    'gather_cooking_fuel': ('采集实际缺少的烹饪煤', 'get cooking coal', 'pickaxe; verified fuel deficit; reachable coal ore',
                            'scan,walk_path,mine_block', 'coal inventory reaches actual cooking target'),
    'eat_carried_food': ('食用背包已有食物恢复饥饿值', 'eat carried food', 'hunger<16; edible stock',
                         'select_item,use_item', 'hunger increases; food consumed'),
    'gather_shelter_material': ('按本世界庇护方案采集缺少的泥土', 'get shelter dirt', 'camp plan; tools; food; dirt deficit',
                               'walk_path,mine_block', 'dirt inventory gain'),
    'build_shelter': ('按已观察方案建造并复核小庇护所', 'build shelter', 'camp plan; tools; food; dirt stock',
                      'slot_click,interact,scan', 'all planned blocks/door scanned'),
    'prepare_small_shelter': ('先建带门小屋并进屋关门', 'prepare small shelter', 'alive; door materials; carried or reachable soil; bounded safe site search',
                              'scan,mine_block,slot_click,interact,walk_path', 'enclosure, real entry and closed door verified'),
    'prepare_sword': ('准备并装备当前可做的剑', 'prepare defensive sword', 'carried sword or actual wood/stone/sticks; station',
                      'select_item,slot_click,interact', 'actual sword inventory and selected hand'),
    'upgrade_stone_sword': ('补齐必要圆石升级石剑', 'upgrade stone sword', 'pickaxe; two actual cobblestone; sticks; station',
                            'mine_block,scan,walk_path,slot_click,select_item', 'stone sword inventory; previous blade preserved'),
    'enter_small_shelter': ('进入已验证小屋关门', 'enter small shelter','same-world verified enclosure; known door; normal path',
                            'scan,interact,walk_path','actual entry; closed door'),
    'leave_small_shelter': ('白天正常出屋继续任务', 'leave small shelter','same-world verified enclosure; known door; safe exit',
                            'scan,interact,walk_path','actual outside position; closed door'),
    'prepare_iron_equipment': ('采集露天铁矿、熔炼并穿戴铁装备', 'prepare iron gear', 'completed camp; tools; food; iron/ore',
                               'mine_block,slot_click', 'iron tools/armor in inventory/equipment'),
    'explore_nearby': ('沿扫描过的安全步行路线探索附近', 'explore nearby', 'new scanned safe path; bounded route',
                       'walk_path,scan', 'current position near route end'),
    'recover_after_death': ('通过游戏正常重生并重新观察环境', 'normal respawn', 'native player death; registered trial',
                            'trial_respawn', 'alive native state; fresh observation'),
    'recover_surface_access': ('保留实体台阶并用有限清障恢复向上通道', 'recover upward access',
                               'pickaxe; grounded; verified step/headroom; no normal exploration route',
                               'scan,mine_block,walk_path', 'native position height gain; surface remains unverified'),
    'wait': ('等待新证据或补齐原生能力', 'wait', 'no action required',
             'none', 'no gameplay action dispatched'),
}

PROGRESSION_GAPS = (
    'nether_portal_construction', 'blaze_rod_collection', 'ender_pearl_collection',
    'stronghold_location_and_portal', 'end_crystal_and_dragon_combat',
)
UNAVAILABLE_MACROS = {}
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
    if action in UNAVAILABLE_MACROS:
        return False
    if action == 'wait':
        return True
    if action == 'recover_after_death':
        return _is_dead(state)
    if _is_dead(state) or state.get('dimension') != 'minecraft:overworld':
        return False
    inv = _inventory(state)
    if action == 'gather_starting_wood':
        from trial_native_chop import supports_native_chop
        return (supports_native_chop(state) and state.get('on_ground') is True
                and state.get('under_water') is not True and not state.get('screen', '')
                and not any(state.get(key) for key in ('chopping', 'navigating', 'borer_active', 'printing')))
    pickaxe = any(inv.get(item, 0) > 0 for item in ('wooden_pickaxe', 'stone_pickaxe', 'iron_pickaxe'))
    if action == 'collect_log_drops':
        entities = state.get('entities')
        if not isinstance(entities, list) or len(entities) > 4096:
            return False
        for entity in entities:
            if (not isinstance(entity, dict) or entity.get('type') != 'minecraft:item'
                    or entity.get('visible') is not True or not isinstance(entity.get('stack'), dict)):
                continue
            item, count = entity['stack'].get('item'), entity['stack'].get('count')
            if (isinstance(item, str) and item.startswith('minecraft:') and item.endswith('_log')
                    and type(count) is int and 0 < count <= 999):
                return True
        return False  # Remembered locations are guidance, not fresh pickup evidence.
    if action == 'craft_wooden_tools':
        wood = sum(n for name, n in inv.items() if name.endswith('_log'))
        planks = sum(n for name, n in inv.items() if name.endswith('_planks'))
        return not pickaxe and (wood >= 4 or planks >= 12)
    if action == 'gather_stone':
        return pickaxe
    if action == 'prepare_small_shelter':
        # candidates() already checked actual carried/reachable soil and the
        # fresh table requirement. Gathering that known soil is this macro's
        # first step, so requiring all 23 dirt in advance would hide it forever.
        door = any(name.endswith('_door') and name != 'iron_door' and count for name,count in inv.items())
        wood = max((inv.get(log + '_planks',0) + 4*inv.get(log + '_log',0)
                    for log in ('oak','spruce','birch','jungle','acacia','dark_oak','mangrove','cherry','pale_oak')), default=0)
        return bool(door or wood >= 6)
    if action == 'prepare_sword':
        return any(n.endswith('_sword') and amount for n,amount in inv.items()) or sum(amount for n,amount in inv.items() if n.endswith('_planks'))+4*sum(amount for n,amount in inv.items() if n.endswith('_log'))>=4
    if action == 'upgrade_stone_sword':
        return pickaxe or inv.get('cobblestone',0)>=2
    if action == 'gather_cooking_fuel':
        return pickaxe
    if action == 'recover_surface_access':
        return pickaxe and state.get('on_ground') is True
    if action == 'craft_stone_tools':
        return pickaxe and inv.get('cobblestone', 0) >= 3
    if action == 'gather_food':
        return inv.get('stone_axe', 0) > 0 or any(inv.get(item, 0) > 0 for item in ('beef', 'porkchop', 'mutton', 'chicken'))
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
    from trial_native_chop import supports_native_chop
    host_blocked = {} if supports_native_chop(state) else {
        'gather_starting_wood': 'native_chopper_trial_flight_and_stop_coordination_pending'}
    result = {'protocol': PROTOCOL, 'scope': 'registered_trial_macros_only',
              'available': [], 'blocked': {**{name: 'unsupported' for name in PROGRESSION_GAPS}, **UNAVAILABLE_MACROS, **host_blocked},
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
        'availability': 'blocked' if action in UNAVAILABLE_MACROS else 'requires_current_prerequisites',
        'parameters_from': 'current_native_skill_not_model',
    } for action, values in CATALOG.items()]
