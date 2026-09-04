package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.chopper.ChopperApproachPolicy;

final class ChopperApproachPolicyTest {
	@Test
	void mineLeavesInReachImmediately() {
		assertTrue(ChopperApproachPolicy.shouldMineBlocker(true, true, true));
		assertFalse(ChopperApproachPolicy.shouldMineBlocker(true, true, false));
		assertFalse(ChopperApproachPolicy.shouldMineBlocker(false, true, true));
		assertFalse(ChopperApproachPolicy.shouldMineBlocker(true, false, true));
	}

	@Test
	void flyOverAfterOneSecondStuck() {
		assertFalse(ChopperApproachPolicy.shouldFlyOver(19));
		assertTrue(ChopperApproachPolicy.shouldFlyOver(20));
		assertTrue(ChopperApproachPolicy.shouldFlyOver(100));
	}

	@Test
	void hoverFiveBlocksAboveStump() {
		assertEquals(76.0, ChopperApproachPolicy.flyOverFeetY(71.0), 0.01);
		assertTrue(ChopperApproachPolicy.shouldAscendOver(72.0, 76.0, 6.5));
		assertFalse(ChopperApproachPolicy.shouldAscendOver(76.0, 76.0, 6.5));
		assertTrue(ChopperApproachPolicy.shouldDescendToDest(76.0, 71.0, 0.5));
		assertFalse(ChopperApproachPolicy.shouldDescendToDest(76.0, 71.0, 4.0));
	}

	@Test
	void inReachStandsStillInsteadOfFlyingCloser() {
		assertFalse(ChopperApproachPolicy.flyWhenInReach());
		assertFalse(ChopperApproachPolicy.walkAfterMineFail(true));
		assertTrue(ChopperApproachPolicy.walkAfterMineFail(false));
		assertTrue(ChopperApproachPolicy.retryIgnoredLeaf(true));
		assertFalse(ChopperApproachPolicy.retryIgnoredLeaf(false));
		assertTrue(ChopperApproachPolicy.retryIgnoredTreeBlock(false, true));
		assertTrue(ChopperApproachPolicy.snapLookWhenInReach(true));
		assertFalse(ChopperApproachPolicy.snapLookWhenInReach(false));
		assertFalse(ChopperApproachPolicy.giveUpStandStill(39));
		assertTrue(ChopperApproachPolicy.giveUpStandStill(40));
	}
}
