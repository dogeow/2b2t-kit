"""Keep an idle owner alive during an unowned trade window, without input."""
from native_outcome_fence import exact_idle_terminal

USER_CONTAINERS = {
    'MerchantScreen': 'MerchantMenu', 'LoomScreen': 'LoomMenu',
    'StonecutterScreen': 'StonecutterMenu', 'ContainerScreen': 'ChestMenu',
    'ShulkerBoxScreen': 'ShulkerBoxMenu', 'CraftingScreen': 'CraftingMenu',
    'AnvilScreen': 'AnvilMenu', 'FurnaceScreen': 'FurnaceMenu',
    'BlastFurnaceScreen': 'BlastFurnaceMenu', 'SmokerScreen': 'SmokerMenu',
    'BrewingStandScreen': 'BrewingStandMenu',
}

def idle_interface_transition(client,state,*,retained_failure=False):
    """Re-observe a user's menu transition without finishing the native owner.

    status() and raw() are different snapshots: the player can close the menu
    between them. An empty second screen requires a new normal status check,
    never a finished heartbeat or permission to execute the queued command.
    """
    screen=state.get('screen');menu=state.get('menu')or{}
    if screen:
        passive_inventory=state.get('interface_paused') is True and menu.get('type')=='InventoryMenu'
        foreign_container=screen in USER_CONTAINERS and menu.get('type')==USER_CONTAINERS[screen]
        if menu.get('material_owned') is True or not (passive_inventory or foreign_container):
            return False
    return bool(not retained_failure and state.get('health')==20
        and state.get('guard_armed')is True and state.get('guard_pve_only')is True
        and not any((state.get('movement_keys')or{}).values())
        and exact_idle_terminal(client,state))

def idle_manual_transition(client,state,*,retained_failure=False):
    """Observe native idle handoff and cooldown without sending game input."""
    return bool(not retained_failure and state.get('manual_material_paused') is True
        and not state.get('screen') and state.get('health')==20
        and state.get('guard_armed') is True and state.get('guard_pve_only') is True
        and exact_idle_terminal(client,state,allow_manual=True))


def idle_foreign_merchant(client,state,*,retained_failure=False):
    """This permits observation only; it never adopts or closes the window."""
    menu=state.get('menu')or{}
    return bool(not retained_failure and state.get('screen')=='MerchantScreen'
        and menu.get('type')=='MerchantMenu'and menu.get('material_owned')is not True
        and state.get('health')==20 and state.get('guard_armed')is True
        and state.get('guard_pve_only')is True
        and not any((state.get('movement_keys')or{}).values())
        and exact_idle_terminal(client,state))
