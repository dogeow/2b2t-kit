"""Client-injected inventory transactions. Observe delayed replies; never repeat ambiguous clicks."""
from __future__ import annotations

import copy
import time
from typing import Callable


def destination_capacity(source: dict, destination: dict) -> int:
    """An empty stack's reported limit is not the receiving slot's capacity."""
    # Minecraft reports ItemStack.EMPTY.getMaxStackSize() as 1. For an empty
    # cell the incoming item's limit applies; occupied cells keep their limit.
    stack = destination if destination['count'] else source
    return stack.get('max_stack', source.get('max_stack', 64))


class InventorySession:
    def __init__(self, client):
        self.client = client
        self.menu_id: int | None = None

    def _bind(self, menu_id: int) -> None:
        if self.menu_id is None:
            self.menu_id = menu_id
        elif self.menu_id != menu_id:
            raise RuntimeError("Container changed during inventory session; no further clicks")

    def _wait(self, state: dict, menu_id: int, predicate: Callable[[dict], bool], stage: str,
              confirmations: int = 1, interval: float = .15) -> dict:
        self._bind(menu_id)
        deadline = time.monotonic() + 6
        seen = 0
        while True:
            menu = state['menu']
            if menu['id'] != menu_id:
                raise RuntimeError(f'Container changed during {stage}; no action replay')
            seen = seen + 1 if predicate(menu) else 0
            if seen >= confirmations:
                return state
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Inventory acknowledgement missing at {stage}; no action replay')
            time.sleep(interval)
            state = self.client.status()

    def click(self, state: dict, slot: int, kind: str = 'pickup', button: int = 0) -> dict:
        menu = state['menu']
        if not 0 <= slot < len(menu['slots']):
            raise ValueError('Inventory slot is outside the current container')
        menu_id = menu['id']
        self._bind(menu_id)
        row = menu['slots'][slot]
        return self.client.checked('slot_click', menu_id=menu_id, slot=slot,
                                   expected_item=row['item'], expected_count=row['count'],
                                   kind=kind, button=button)

    @staticmethod
    def _stack_identity(row: dict) -> tuple:
        return (row['item'] if row['count'] else 'minecraft:air', row['count'])

    def _refresh_furnace_after_rejection(self, before: dict, source_slot: int, cell: int) -> dict:
        """Observe a natural furnace tick after a proved pre-click rejection."""
        same = self._stack_identity
        for observation in range(11):
            state = self.client.status()
            menu = state['menu']
            if (menu['id'] != before['id'] or menu['type'] != 'FurnaceMenu'
                    or len(menu['slots']) != len(before['slots'])
                    or same(menu['cursor']) != same(before['cursor'])
                    or any(same(a) != same(b) for a, b in zip(menu['slots'][3:], before['slots'][3:]))
                    or same(menu['slots'][source_slot]) != same(before['slots'][source_slot])):
                raise RuntimeError('Furnace transfer context changed after rejection; no action replay')
            old, fresh = before['slots'][:3], menu['slots'][:3]
            # Only ordinary consumption is admissible: input becomes output,
            # fuel may decrease, and neither user inventory nor cursor moves.
            if (fresh[0]['count'] > old[0]['count'] or fresh[1]['count'] > old[1]['count']
                    or fresh[2]['count'] < old[2]['count']
                    or fresh[0]['count'] + fresh[2]['count'] != old[0]['count'] + old[2]['count']
                    or any(fresh[i]['count'] and old[i]['count'] and fresh[i]['item'] != old[i]['item'] for i in range(3))
                    or fresh[cell]['count'] and fresh[cell]['item'] != before['cursor']['item']):
                raise RuntimeError('Furnace contents changed beyond consumption; no action replay')
            if fresh[cell]['count'] < old[cell]['count']:
                return state
            if observation < 10:
                time.sleep(.1)
        raise RuntimeError('Furnace consumption was not confirmed after rejection; no action replay')

    def _place_furnace_click(self, state: dict, source_slot: int, cell: int, button: int) -> dict:
        # These exact native errors precede handleContainerInput. An uncertain
        # reply, timeout, source-slot action, or non-furnace click never retries.
        for attempt in range(3):
            before = copy.deepcopy(state['menu'])
            try:
                return self.click(state, cell, button=button)
            except RuntimeError as error:
                if (str(error) not in ('Slot item changed', 'Slot count changed')
                        or before['type'] != 'FurnaceMenu' or cell not in (0, 1)
                        or source_slot < 3 or not before['cursor']['count']):
                    raise
                if attempt == 2:
                    raise RuntimeError('Furnace pre-click rejection limit reached; no further clicks') from error
                state = self._refresh_furnace_after_rejection(before, source_slot, cell)

    def _cursor(self, state: dict, menu_id: int, item: str, count: int, stage: str) -> dict:
        return self._wait(state, menu_id,
                          lambda menu: menu['cursor']['count'] == count and (not count or menu['cursor']['item'] == item), stage)

    @staticmethod
    def _expect_slot(state: dict, slot: int, item: str, count: int) -> None:
        row = state['menu']['slots'][slot]
        if row['count'] != count or count and row['item'] != item:
            raise RuntimeError('Inventory cell changed during transaction; no further clicks')

    def place_cell(self, state: dict, source: dict, cell: int, amount: int, *, append: bool = False) -> dict:
        """Place an exact amount; append only to same-item furnace inputs/fuel.

        The furnace caller owns the recipe journal and must check input/output
        conservation across additions because smelting can consume either cell.
        """
        menu = state['menu']
        source_slot, size, item = source['slot'], source['count'], source['item']
        if (isinstance(amount, bool) or not isinstance(amount, int) or not 1 <= amount <= size
                or cell == source_slot or not 0 <= cell < len(menu['slots'])
                or menu['cursor']['count']
                or append and (menu['type'] != 'FurnaceMenu' or cell not in (0, 1))):
            raise ValueError('Expected an empty cursor/cell and an exact available ingredient amount')
        initial = menu['slots'][cell]['count']
        if (initial and (not append or menu['slots'][cell]['item'] != item)
                or initial + amount > destination_capacity(source, menu['slots'][cell])):
            raise ValueError('Furnace append requires the same item and enough capacity')
        actual_source = menu['slots'][source_slot]
        if actual_source['item'] != item or actual_source['count'] != size:
            raise RuntimeError('Ingredient source changed before placement')
        menu_id = menu['id']
        self._bind(menu_id)
        crafting = menu['type'] in ('CraftingMenu', 'InventoryMenu')

        def expect_cell(current: dict, added: int) -> None:
            row = current['menu']['slots'][cell]
            if crafting:
                self._expect_slot(current, cell, item, initial + added)
            elif row['count'] > initial + added or row['count'] and row['item'] != item:
                raise RuntimeError('Furnace cell changed during transaction')

        def place(current: dict, button: int) -> dict:
            if menu['type'] == 'FurnaceMenu' and cell in (0, 1):
                return self._place_furnace_click(current, source_slot, cell, button)
            return self.click(current, cell, button=button)

        half = (size + 1) // 2
        picked = half if amount <= half and amount < size else size
        direct = amount < picked - amount
        if direct and menu['type'] == 'FurnaceMenu' and cell in (0, 1):
            # Repeated right-click deposits race furnace slot corrections. Split
            # on a stable player slot, then send the exact stack in one click.
            # This costs two extra clicks for small batches, not dozens of
            # remainder clicks on a half stack. No ambiguous step is replayed.
            staging = next((row for row in menu['slots'][3:]
                            if row['slot'] != source_slot and not row['count']), None)
            if staging is not None:
                from kit_runtime.storage import move_amount
                state = move_amount(self, state, source, staging, amount)
                staged = state['menu']['slots'][staging['slot']]
                return self.place_cell(state, staged, cell, amount, append=append)
            # A full inventory has no scratch slot. Keep the exact remainder
            # on the source side, even though this slower path needs more clicks.
            direct = False
        state = self.click(state, source_slot, button=0 if direct else int(picked != size))
        cursor_start = size if direct else picked
        state = self._wait(state, menu_id,
                           lambda m: m['cursor']['item'] == item and m['cursor']['count'] == cursor_start
                           and m['slots'][source_slot]['count'] == size - cursor_start,
                           'ingredient_pickup')
        if direct:
            for placed in range(amount):
                expect_cell(state, placed)
                state = place(state, 1)
                state = self._cursor(state, menu_id, item, size - placed - 1, 'ingredient_cell')
            self._expect_slot(state, source_slot, item, 0)
            state = self.click(state, source_slot)
        else:
            for returned in range(picked - amount):
                self._expect_slot(state, source_slot, item, size - picked + returned)
                state = self.click(state, source_slot, button=1)
                remaining = picked - returned - 1
                source_count = size - picked + returned + 1
                state = self._wait(state, menu_id, lambda m: m['cursor']['count'] == remaining and m['cursor']['item'] == item
                                   and m['slots'][source_slot]['count'] == source_count and m['slots'][source_slot]['item'] == item, 'ingredient_remainder')
            expect_cell(state, 0)
            state = place(state, 0)
        # Furnace fuel may start burning immediately. The furnace executor checks
        # its recipe balance separately; crafting cells must retain the exact count.
        return self._wait(state, menu_id,
                          lambda m: not m['cursor']['count'] and m['slots'][source_slot]['count'] == size - amount
                          and (size == amount or m['slots'][source_slot]['item'] == item)
                          and (not crafting or m['slots'][cell]['item'] == item and m['slots'][cell]['count'] == amount),
                          'ingredient_placed')

    def wait_grid(self, state: dict, menu_id: int, item: str, cells: list[int], amount: int) -> dict:
        return self._wait(state, menu_id,
                          lambda m: not m['cursor']['count'] and all(m['slots'][i]['item'] == item and m['slots'][i]['count'] == amount for i in cells),
                          'crafting_grid', confirmations=2, interval=.2)

    def wait_recipe(self, state: dict, output: str) -> dict:
        return self._wait(state, state['menu']['id'], lambda m: m['slots'][0]['item'] == output, 'recipe_output', interval=.25)
