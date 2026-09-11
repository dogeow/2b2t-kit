package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.ArrayList;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoPolicyTest {
	private BorerCargoPolicy.Stack stack(String id, int count) { return new BorerCargoPolicy.Stack("minecraft:" + id, count, false); }
	@Test void ordinaryStonesAreExplicitlyRecognisedButEveryOreAndToolIsSafeFromDiscard() {
		for (String id : BorerCargoPolicy.STONE) assertTrue(BorerCargoPolicy.stone("minecraft:" + id));
		for (String id : List.of("lapis_lazuli", "lapis_block", "gold_ore", "raw_gold", "gold_ingot", "diamond", "deepslate_diamond_ore",
			"redstone", "emerald", "coal", "quartz", "ancient_debris", "diamond_pickaxe", "bow", "arrow", "water_bucket", "chest")) {
			assertFalse(BorerCargoPolicy.stone("minecraft:" + id), id);
		}
		assertFalse(BorerCargoPolicy.stone("custom:stone"));
	}
	@Test void dropsOnlySurplusStoneAndKeepsOneStackOfBuildingMaterial() {
		var stacks = List.of(stack("cobblestone", 64), stack("lapis_lazuli", 64), stack("deepslate", 64), stack("gold_ingot", 64));
		assertEquals(2, BorerCargoPolicy.next(stacks, true));
		assertEquals(1, BorerCargoPolicy.next(stacks, false));
	}
	@Test void reserveWorksAcrossSplitStacksAndDifferentStoneTypes() {
		var stacks = List.of(stack("stone", 32), stack("tuff", 32), stack("granite", 64));
		assertArrayEquals(new boolean[]{true, true, false}, BorerCargoPolicy.reserved(stacks));
		assertEquals(2, BorerCargoPolicy.next(stacks, true));
	}
	@Test void storageKeepsEquipmentSuppliesChestsAndCoalReserve() {
		var stacks = new ArrayList<BorerCargoPolicy.Stack>();
		for (String id : List.of("diamond_pickaxe", "bow", "arrow", "torch", "bread", "water_bucket", "chest", "coal", "cobblestone")) stacks.add(stack(id, 64));
		assertEquals(-1, BorerCargoPolicy.next(stacks, false));
		stacks.add(stack("coal", 64));
		assertEquals(9, BorerCargoPolicy.next(stacks, false));
	}
	@Test void namedOrModifiedResourcesAreNeverAutomaticallyTransferred() {
		var stacks = List.of(new BorerCargoPolicy.Stack("minecraft:stone", 64, true), new BorerCargoPolicy.Stack("minecraft:diamond", 64, true));
		assertEquals(-1, BorerCargoPolicy.next(stacks, true));
		assertEquals(-1, BorerCargoPolicy.next(stacks, false));
	}
	@Test void onlyNearFullBagsTriggerAndStationIsOutsideEvenAtNegativeCoordinates() {
		assertFalse(BorerCargoPolicy.nearFull(4)); assertTrue(BorerCargoPolicy.nearFull(3)); assertTrue(BorerCargoPolicy.nearFull(0));
		assertFalse(BorerCargoPolicy.outside(-5, -5, -10, -10, 0, 0));
		assertFalse(BorerCargoPolicy.outside(-13, -5, -10, -10, 0, 0));
		assertTrue(BorerCargoPolicy.outside(-14, -5, -10, -10, 0, 0));
		assertTrue(BorerCargoPolicy.outside(-5, 4, -10, -10, 0, 0));
	}
}
