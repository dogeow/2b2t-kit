package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.chopper.ChopperToolPolicy;

final class ChopperToolPolicyTest {
	@Test
	void shearsBelowMeteorAntiBreakPercentAreWorn() {
		assertTrue(ChopperToolPolicy.tooWorn(20, 238));
		assertTrue(ChopperToolPolicy.tooWorn(8, 238));
		assertFalse(ChopperToolPolicy.tooWorn(24, 238));
		assertFalse(ChopperToolPolicy.tooWorn(200, 238));
	}

	@Test
	void pickaxeEightUsesLeftIsWorn() {
		assertTrue(ChopperToolPolicy.tooWorn(8, 1561));
		assertFalse(ChopperToolPolicy.tooWorn(160, 1561));
	}

	@Test
	void wornCurrentToolIsReplacedByAUsableHotbarToolBeforeInventory() {
		int[] remaining = {0, 200, 0, 8, 0, 0, 0, 0, 0, 238};
		assertEquals(1, ChopperToolPolicy.chooseSlot(3, remaining.length,
			slot -> !ChopperToolPolicy.tooWorn(remaining[slot], 238)));
	}

	@Test
	void usableCurrentToolStaysSelectedAndInventoryIsUsedWhenNeeded() {
		assertEquals(4, ChopperToolPolicy.chooseSlot(4, 36, slot -> slot == 1 || slot == 4 || slot == 12));
		assertEquals(12, ChopperToolPolicy.chooseSlot(4, 36, slot -> slot == 12));
		assertEquals(-1, ChopperToolPolicy.chooseSlot(4, 36, slot -> false));
	}

	@Test
	void indestructibleItemsAndBoundaryDurabilityRemainUsable() {
		assertFalse(ChopperToolPolicy.tooWorn(0, 0));
		assertTrue(ChopperToolPolicy.tooWorn(22, 238));
		assertFalse(ChopperToolPolicy.tooWorn(23, 238));
	}
}
