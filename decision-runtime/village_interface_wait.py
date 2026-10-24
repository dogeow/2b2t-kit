"""Keep an idle owner alive during an unowned trade window, without input."""
from native_outcome_fence import exact_idle_terminal


def idle_interface_transition(client,state,*,retained_failure=False):
    """Re-observe a user's menu transition without finishing the native owner.

    status() and raw() are different snapshots: the player can close the menu
    between them. An empty second screen requires a new normal status check,
    never a finished heartbeat or permission to execute the queued command.
    """
    screen=state.get('screen');menu=state.get('menu')or{}
    expected={'MerchantScreen':'MerchantMenu','LoomScreen':'LoomMenu',
              'StonecutterScreen':'StonecutterMenu'}
    if screen:
        if screen not in expected or menu.get('type')!=expected[screen]or menu.get('material_owned')is True:
            return False
    return bool(not retained_failure and state.get('health')==20
        and state.get('guard_armed')is True and state.get('guard_pve_only')is True
        and not any((state.get('movement_keys')or{}).values())
        and exact_idle_terminal(client,state))


def idle_foreign_merchant(client,state,*,retained_failure=False):
    """This permits observation only; it never adopts or closes the window."""
    menu=state.get('menu')or{}
    return bool(not retained_failure and state.get('screen')=='MerchantScreen'
        and menu.get('type')=='MerchantMenu'and menu.get('material_owned')is not True
        and state.get('health')==20 and state.get('guard_armed')is True
        and state.get('guard_pve_only')is True
        and not any((state.get('movement_keys')or{}).values())
        and exact_idle_terminal(client,state))
