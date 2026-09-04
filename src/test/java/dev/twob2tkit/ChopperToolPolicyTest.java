package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
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
	void noUsableShearsMeansFist() {
		assertTrue(ChopperToolPolicy.useFistForLeaves(false));
		assertFalse(ChopperToolPolicy.useFistForLeaves(true));
		assertTrue(ChopperToolPolicy.keepCurrentTool(true, false));
		assertFalse(ChopperToolPolicy.keepCurrentTool(true, true));
		assertFalse(ChopperToolPolicy.keepCurrentTool(false, false));
	}
}
