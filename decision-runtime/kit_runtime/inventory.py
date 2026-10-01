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
              confirmations: int = 1, interval: float = .15,
              *, fresh: bool = False) -> dict:
        """Wait for a menu state without treating an optimistic click reply as an ack.

        ``checked(slot_click)`` can return Minecraft's locally predicted menu before
        a late server correction arrives.  For a dependent inventory mutation,
        callers set ``fresh`` and require two later, time-advanced observations.
        This spans the brief prediction/correction/final-confirmation sequence while
        still never replaying the already dispatched click.
        """
        self._bind(menu_id)
        deadline = time.monotonic() + 6
        seen = 0
        first = True
        last_observed_time = state.get('time')
        poll_interval = interval if isinstance(last_observed_time, (int, float)) else 0
        while True:
            menu = state['menu']
            if menu['id'] != menu_id:
                raise RuntimeError(f'Container changed during {stage}; no action replay')
            observed_time = state.get('time')
            time_advanced = (not fresh or not first and
                             (not isinstance(last_observed_time, (int, float))
                              or not isinstance(observed_time, (int, float))
                              or observed_time > last_observed_time))
            if time_advanced:
                seen = seen + 1 if predicate(menu) else 0
                if isinstance(observed_time, (int, float)):
                    last_observed_time = observed_time
                if seen >= confirmations:
                    return state
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Inventory acknowledgement missing at {stage}; no action replay')
            time.sleep(poll_interval)
            state = self.client.status()
            first = False

    def click(self, state: dict, slot: int, kind: str = 'pickup', button: int = 0) -> dict:
        menu = state['menu']
        if not 0 <= slot < len(menu['slots']):
            raise ValueError('Inventory slot is outside the current container')
        menu_id = menu['id']
        self._bind(menu_id)
        row = menu['slots'][slot]
        cursor = menu['cursor']
        return self.client.checked('slot_click', menu_id=menu_id, slot=slot,
                                   expected_item=row['item'], expected_count=row['count'],
                                   expected_cursor=cursor['item'] if cursor['count'] else 'minecraft:air',
                                   expected_cursor_count=cursor['count'],
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

    def _wait_pickup(self, state: dict, menu_id: int, source_slot: int, item: str,
                     cursor_count: int, source_count: int, *, full_stack: bool,
                     settle_prediction: bool = False) -> dict:
        """Observe one already-dispatched pickup, including same-item collection.

        A native full-stack pickup can be acknowledged before a nearby dropped
        item is collected.  The first synchronized menu snapshot may therefore
        contain more of the same item on the cursor than the clicked source
        held, or the emptied source may already have been replenished.  The
        dispatched stack on the formerly empty cursor proves the pickup; no
        other mismatch is safe to interpret or replay.
        """
        def acknowledged(menu: dict) -> bool:
            cursor = menu['cursor']
            source = menu['slots'][source_slot]
            exact = (cursor['item'] == item and cursor['count'] == cursor_count
                     and source['count'] == source_count
                     and (not source_count or source['item'] == item))
            if exact:
                return True
            limit = cursor.get('max_stack', 64)
            source_valid = (0 <= source['count'] <= source.get('max_stack', 64)
                            and (not source['count'] or source['item'] == item))
            return (full_stack and source_count == 0 and source_valid
                    and cursor['item'] == item
                    and cursor_count <= cursor['count'] <= limit)
        return self._wait(state, menu_id, acknowledged, 'ingredient_pickup',
                          confirmations=2 if settle_prediction else 1,
                          interval=.1, fresh=settle_prediction)

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
        requested_pickup = half if amount <= half and amount < size else size
        direct = amount < requested_pickup - amount
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
        state = self.click(state, source_slot, button=0 if direct else int(requested_pickup != size))
        expected_cursor = size if direct else requested_pickup
        expected_source = size - expected_cursor
        state = self._wait_pickup(state, menu_id, source_slot, item,
                                  expected_cursor, expected_source,
                                  full_stack=expected_cursor == size,
                                  settle_prediction=crafting)
        cursor_start = state['menu']['cursor']['count']
        source_start = state['menu']['slots'][source_slot]['count']
        observed_total = cursor_start + source_start
        returning = cursor_start - amount
        if (returning and source_start + returning
                > destination_capacity(state['menu']['cursor'], state['menu']['slots'][source_slot])):
            raise RuntimeError('Collected ingredients no longer fit the source slot; no further clicks')
        if direct:
            for placed in range(amount):
                expect_cell(state, placed)
                state = place(state, 1)
                expected_cursor = cursor_start - placed - 1
                state = self._wait(
                    state, menu_id,
                    lambda m, expected_cursor=expected_cursor, placed=placed:
                        m['cursor']['count'] == expected_cursor
                        and (not expected_cursor or m['cursor']['item'] == item)
                        and m['slots'][cell]['item'] == item
                        and m['slots'][cell]['count'] == initial + placed + 1,
                    'ingredient_cell', confirmations=2 if crafting else 1,
                    interval=.1, fresh=crafting)
            self._expect_slot(state, source_slot, item, source_start)
            state = self.click(state, source_slot)
        else:
            for returned in range(cursor_start - amount):
                self._expect_slot(state, source_slot, item, source_start + returned)
                state = self.click(state, source_slot, button=1)
                remaining = cursor_start - returned - 1
                source_count = source_start + returned + 1
                state = self._wait(
                    state, menu_id,
                    lambda m, remaining=remaining, source_count=source_count:
                        m['cursor']['count'] == remaining
                        and (not remaining or m['cursor']['item'] == item)
                        and m['slots'][source_slot]['count'] == source_count
                        and m['slots'][source_slot]['item'] == item,
                    'ingredient_remainder', confirmations=2 if crafting else 1,
                    interval=.1, fresh=crafting)
            expect_cell(state, 0)
            state = place(state, 0)
        # Furnace fuel may start burning immediately. The furnace executor checks
        # its recipe balance separately; crafting cells must retain the exact count.
        final_source = observed_total - amount
        return self._wait(state, menu_id,
                          lambda m: not m['cursor']['count'] and m['slots'][source_slot]['count'] == final_source
                          and (not final_source or m['slots'][source_slot]['item'] == item)
                          and (not crafting or m['slots'][cell]['item'] == item and m['slots'][cell]['count'] == amount),
                          'ingredient_placed', confirmations=2 if crafting else 1,
                          interval=.1, fresh=crafting)

    def wait_grid(self, state: dict, menu_id: int, item: str, cells: list[int], amount: int) -> dict:
        return self._wait(state, menu_id,
                          lambda m: not m['cursor']['count'] and all(m['slots'][i]['item'] == item and m['slots'][i]['count'] == amount for i in cells),
                          'crafting_grid', confirmations=2, interval=.2)

    def wait_recipe(self, state: dict, output: str) -> dict:
        return self._wait(state, state['menu']['id'], lambda m: m['slots'][0]['item'] == output, 'recipe_output', interval=.25)
