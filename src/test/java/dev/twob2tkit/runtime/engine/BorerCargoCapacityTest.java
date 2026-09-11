package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoCapacityTest {
	private BorerCargoCapacity.Slot slot(String id, int count, int max) { return new BorerCargoCapacity.Slot("minecraft:" + id, count, max, true); }
	@Test void exactlyFullSingleOrDoubleChestIsRecordedImmediately() {
		for (int slots : new int[]{27, 54}) {
			var full = BorerCargoCapacity.of(java.util.Collections.nCopies(slots, slot("stone", 64, 64)));
			assertTrue(full.full()); assertTrue(full.accepts().isEmpty());
		}
	}
	@Test void partialStackWithoutEmptySlotsOnlyAcceptsMatchingMaterials() {
		var c = BorerCargoCapacity.of(List.of(slot("stone", 64, 64), slot("diamond", 3, 64)));
		assertFalse(c.full()); assertEquals(List.of("minecraft:diamond"), c.accepts());
	}
	@Test void anyEmptySlotPermitsOtherCargoAndNonStackableItemsUseTheirActualLimit() {
		var c = BorerCargoCapacity.of(List.of(slot("diamond_pickaxe", 1, 1), slot("air", 0, 64)));
		assertFalse(c.full()); assertNull(c.accepts());
		assertTrue(BorerCargoCapacity.of(List.of(slot("diamond_pickaxe", 1, 1))).full());
	}
	@Test void namedPartialStacksAreNotAssumedToMergeWithOrdinaryOre() {
		var c = BorerCargoCapacity.of(List.of(new BorerCargoCapacity.Slot("minecraft:diamond", 2, 64, false)));
		assertFalse(c.full()); assertTrue(c.accepts().isEmpty());
	}
	@Test void nextDepositSkipsAnUnmergeableStoneAndStillUsesTheChestsDiamondSpace() {
		var bag = List.of(new BorerCargoPolicy.Stack("minecraft:cobblestone", 64, false),
			new BorerCargoPolicy.Stack("minecraft:stone", 64, false), new BorerCargoPolicy.Stack("minecraft:diamond", 32, false));
		assertEquals(1, BorerCargoPolicy.next(bag, false));
		assertEquals(2, BorerCargoPolicy.next(bag, false, i -> i == 2));
		assertEquals(-1, BorerCargoPolicy.next(bag, false, i -> false));
		assertEquals(-1, BorerCargoPolicy.next(bag, false, i -> i == 0), "Reserved building blocks must stay reserved");
	}
}
