"""Visible storage identity across shallow nested and full menu snapshots.

AutomationBridge.addItemDetails omits nested CONTAINER details, while stack()
includes them. Only explicitly witnessed empty containers may be normalized;
nonempty contents and every other visible component remain distinct.
"""
from copy import deepcopy
from anvil_enchant_preview import stack_key


def visible_key(row, *, witnessed_empty_items=()):
    value=deepcopy(row)
    if value.get('item') in witnessed_empty_items and value.get('contains') == []:
        value.pop('contains')
    return stack_key(value)
