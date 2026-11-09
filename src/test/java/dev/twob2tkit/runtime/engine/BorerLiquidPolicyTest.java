package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class BorerLiquidPolicyTest {
	@Test
	void oneBlockDripIsALeakLakeIsSkipped() {
		assertTrue(BorerLiquidPolicy.isSmallLeak(1, 4));
		assertTrue(BorerLiquidPolicy.isSmallLeak(0, 1));
		assertFalse(BorerLiquidPolicy.isSmallLeak(1, 0));
		assertFalse(BorerLiquidPolicy.isSmallLeak(3, 2));
		assertTrue(BorerLiquidPolicy.isLake(3));
		assertFalse(BorerLiquidPolicy.isLake(2));
		assertTrue(BorerLiquidPolicy.skipShaftForLake(true, 4));
		assertFalse(BorerLiquidPolicy.skipShaftForLake(false, 4));
		assertTrue(BorerLiquidPolicy.ignoreLakeCandidate(true, 5));
		assertFalse(BorerLiquidPolicy.ignoreLakeCandidate(true, 1));
	}

	@Test
	void walkOverToPlugAFarLeakAndGiveUpAfterRetries() {
		assertTrue(BorerLiquidPolicy.shouldWalkToLeak(true, false, 1.0, false));
		assertFalse(BorerLiquidPolicy.shouldWalkToLeak(true, true, 4.0, false));
		assertTrue(BorerLiquidPolicy.shouldWalkToLeak(true, true, 4.0, true));
		assertFalse(BorerLiquidPolicy.shouldWalkToLeak(true, true, 1.0, true));
		assertFalse(BorerLiquidPolicy.shouldWalkToLeak(true, true, 1.0, false));
		assertFalse(BorerLiquidPolicy.shouldWalkToLeak(false, false, 9.0, false));
		assertFalse(BorerLiquidPolicy.giveUpAfterFails(2));
		assertTrue(BorerLiquidPolicy.giveUpAfterFails(3));
		assertEquals(6, BorerLiquidPolicy.settleTicks(true, true));
		assertEquals(0, BorerLiquidPolicy.settleTicks(false, true));
		assertEquals(4, BorerLiquidPolicy.settleTicks(false, false));
	}
	@Test
	void lavaContactPrefersGroundRetreatAndNeverEnablesFlight() {
		assertTrue(BorerLiquidPolicy.preferGroundRetreatFromLava(true, true));
		assertFalse(BorerLiquidPolicy.preferGroundRetreatFromLava(true, false));
		assertFalse(BorerLiquidPolicy.preferGroundRetreatFromLava(false, true));
		assertFalse(BorerLiquidPolicy.allowEnableFlightForLava(false));
		assertFalse(BorerLiquidPolicy.allowEnableFlightForLava(true));
		assertTrue(BorerLiquidPolicy.stopInsteadOfFlightThrash(true, false));
		assertFalse(BorerLiquidPolicy.stopInsteadOfFlightThrash(true, true));
		assertFalse(BorerLiquidPolicy.stopInsteadOfFlightThrash(false, false));
	}

	@Test
	void standingOnMagmaKeepsDiggingTheMagmaExitInsteadOfResettingEveryTick() {
		// 2026-11-03: "脚下岩浆块，潜行并挖开离开" for 60s with no progress while mining magma.
		assertTrue(BorerLiquidPolicy.keepMagmaExitDig(true, false, false, true));
		assertFalse(BorerLiquidPolicy.keepMagmaExitDig(true, true, false, true));
		assertFalse(BorerLiquidPolicy.keepMagmaExitDig(true, false, true, true));
		assertFalse(BorerLiquidPolicy.keepMagmaExitDig(true, false, false, false));
		assertFalse(BorerLiquidPolicy.keepMagmaExitDig(false, false, false, true));
	}

	@Test
	void magmaMiningCrouchesOnMagmaUnlessLavaIsBesideOrBelow() {
		// 2026-11-03: mining magma flew away ("飞行离开") instead of crouching on the vein.
		assertTrue(BorerLiquidPolicy.sneakOnMagma(true, true, false, false, false));
		assertFalse(BorerLiquidPolicy.sneakOnMagma(true, true, false, false, true));
		assertFalse(BorerLiquidPolicy.sneakOnMagma(true, true, true, false, false));
		assertFalse(BorerLiquidPolicy.sneakOnMagma(true, true, false, true, false));
		assertFalse(BorerLiquidPolicy.sneakOnMagma(true, false, false, false, false));
		assertFalse(BorerLiquidPolicy.sneakOnMagma(false, true, false, false, false));
	}

	@Test
	void flatMagmaRouteIgnoresLavaUnderAnUnminedFloorButDescentStaysStrict() {
		// 2026-11-03: lava two blocks under the floor (y26) skipped every magma target as "挡住通往矿脉的通路".
		assertTrue(BorerLiquidPolicy.ignoreLiquidUnderFloor(true, 0));
		assertTrue(BorerLiquidPolicy.ignoreLiquidUnderFloor(true, 4));
		assertFalse(BorerLiquidPolicy.ignoreLiquidUnderFloor(true, -1));
		assertFalse(BorerLiquidPolicy.ignoreLiquidUnderFloor(false, 0));
	}

	@Test
	void magmaMiningMayStepOntoMagmaWithoutLavaToPickUpDrops() {
		// 2026-11-03: a magma drop resting on magma 3 blocks away was deferred after 8 idle seconds.
		assertTrue(BorerLiquidPolicy.safeMagmaFloor(true, true, false));
		assertFalse(BorerLiquidPolicy.safeMagmaFloor(true, true, true));
		assertFalse(BorerLiquidPolicy.safeMagmaFloor(false, true, false));
		assertFalse(BorerLiquidPolicy.safeMagmaFloor(true, false, false));
	}

	@Test
	void shortDropOntoSafeMagmaIsWalkedNotPaved() {
		// 2026-11-03: kept placing a support block above magma and mining it again.
		assertTrue(BorerLiquidPolicy.dropOntoSafeMagma(0, true));
		assertTrue(BorerLiquidPolicy.dropOntoSafeMagma(3, true));
		assertFalse(BorerLiquidPolicy.dropOntoSafeMagma(4, true));
		assertFalse(BorerLiquidPolicy.dropOntoSafeMagma(1, false));
	}
}
