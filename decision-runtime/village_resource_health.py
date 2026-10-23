"""Scope a resource trip's NPC health checks to its witnessed home cohort.

The caller must retain its existing native lease/status checks. This does not
clear a safety hold, acquire ownership, or permit an injured player to move.
"""
import math
import copy
import json
import uuid
from pathlib import Path


class ProtectedResidentHealthError(RuntimeError):
    """Retain the exact failing observation before a later frame can replace it."""
    def __init__(self, resident, state):
        self.resident = copy.deepcopy(resident)
        self.snapshot = copy.deepcopy(state)
        super().__init__('Protected village resident health is unsafe: '
                         f'uuid={resident.get("uuid")} health={resident.get("health")} '
                         f'pos={resident.get("pos")} observed_at={state.get("time")}')


def record_health_failure(directory, error):
    """Write one immutable local diagnostic; never perform any game operation."""
    if not isinstance(error, ProtectedResidentHealthError):
        raise TypeError('Exact protected resident health failure required')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('resident-health-failure-' + uuid.uuid4().hex + '.json')
    data = {'schema': 1, 'scope': 'exact_client_guard_failure_not_damage_cause_or_death_proof',
            'world_session': error.snapshot.get('world_session'),
            'observed_at': error.snapshot.get('time'), 'resident': error.resident,
            'original_snapshot': error.snapshot, 'game_operations': 0,
            'safety_lock_cleared': False, 'reconnect_authorized': False}
    with path.open('x', encoding='utf-8') as target:
        json.dump(data, target, ensure_ascii=False, indent=2)
        target.write('\n')
    return path


def check(state, world, protected_uuids, home_min, home_max, *, owned_menu=None):
    menu = state.get('menu') or {}
    lease = state.get('supervision_lease') or {}
    certified_type = (owned_menu or {}).get('type')
    screen_for_menu = {'ChestMenu': 'ContainerScreen', 'AnvilMenu': 'AnvilScreen'}
    anvil_intent = (certified_type != 'AnvilMenu' or
                   owned_menu.get('purpose') == 'name_tag_rename'
                   and isinstance(owned_menu.get('source_request'), str)
                   and bool(owned_menu['source_request']))
    owned_storage = (isinstance(owned_menu, dict)
                     and certified_type in screen_for_menu and anvil_intent
                     and state.get('screen') == screen_for_menu[certified_type]
                     and state.get('interface_paused') is False
                     and state.get('inventory_interface_paused') is False
                     and menu.get('type') == certified_type
                     and type(menu.get('id')) is int and menu['id'] > 0
                     and menu['id'] == owned_menu.get('id')
                     and menu.get('cursor', {}).get('count') == 0
                     and lease.get('kind') == 'materials'
                     and lease.get('world_session') == world == owned_menu.get('world_session')
                     and bool(lease.get('id')) and lease['id'] == owned_menu.get('lease_id')
                     and bool(lease.get('job_session'))
                     and lease['job_session'] == owned_menu.get('task_session')
                     and type(state.get('control_revision')) is int
                     and state['control_revision'] == owned_menu.get('control_revision'))
    merchant = menu.get('merchant') or {}
    owned_merchant = (state.get('screen') == 'MerchantScreen'
                      and menu.get('type') == 'MerchantMenu'
                      and menu.get('material_owned') is True
                      and type(menu.get('id')) is int and menu['id'] > 0
                      and state.get('interface_paused') is False
                      and state.get('inventory_interface_paused') is False
                      and menu.get('cursor', {}).get('count') == 0
                      and len(menu.get('slots', [])) >= 3
                      and all(row.get('count') == 0 for row in menu['slots'][:3])
                      and lease.get('kind') == 'materials' and bool(lease.get('id'))
                      and lease.get('world_session') == world
                      and bool(lease.get('job_session'))
                      and merchant.get('protocol') == 1 and merchant.get('owned') is True
                      and merchant.get('owner_task') == lease['job_session']
                      and merchant.get('menu_id') == menu['id']
                      and merchant.get('villager_uuid') in protected_uuids
                      and isinstance(merchant.get('opening_request_id'), str)
                      and bool(merchant['opening_request_id']))
    if (not isinstance(world, str) or not world
            or state.get('connected') is not True or state.get('world_session') != world
            or state.get('health') != 20 or state.get('manual_movement') is not False
            or state.get('screen') != '' and not (owned_storage or owned_merchant)
            or state.get('health_recovery_hold')
            or state.get('safety_hold', {}).get('active')):
        raise RuntimeError('Resource trip lost healthy current player control')
    if (not isinstance(protected_uuids, (set, frozenset)) or not protected_uuids
            or any(not isinstance(v, str) or not v for v in protected_uuids)
            or len(home_min) != 3 or len(home_max) != 3
            or any(type(v) is not int for v in (*home_min, *home_max))
            or any(a > b for a, b in zip(home_min, home_max))):
        raise ValueError('Witnessed cohort and exact home bounds required')
    for row in state.get('loaded_villagers', {}).get('villagers', []):
        pos = row.get('pos')
        if (not isinstance(row.get('uuid'), str) or not isinstance(pos, list)
                or len(pos) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in pos)):
            raise RuntimeError('Cannot scope an incomplete villager observation')
        at_home = all(a <= v < b + 1 for a, v, b in zip(home_min, pos, home_max))
        if (row['uuid'] in protected_uuids or at_home) and row.get('health') != 20:
            raise ProtectedResidentHealthError(row, state)
    return state
