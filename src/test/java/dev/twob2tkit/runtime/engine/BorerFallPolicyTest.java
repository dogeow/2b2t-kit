package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住 2026-08-15 的落差约定，避免再被「空气就铺路 / 只许下 1 格」盖掉。
 */
final class BorerFallPolicyTest {
	@Test
	void withoutNoFallMaxIsThreeBlocks() {
		assertEquals(3, BorerFallPolicy.maxSafeFallBlocks(false));
	}

	@Test
	void withNoFallMaxIsFortyEightBlocks() {
		assertEquals(48, BorerFallPolicy.maxSafeFallBlocks(true));
	}

	@Test
	void oneTwoAndThreeBlockDropsAreWalkableWithoutNoFall() {
		for (int drop : new int[]{1, 2, 3}) {
			assertTrue(BorerFallPolicy.canWalk(drop), "drop=" + drop);
			assertTrue(BorerFallPolicy.shouldWalkIntoDrop(drop), "drop=" + drop);
			assertFalse(BorerFallPolicy.shouldBridge(drop), "drop=" + drop);
		}
	}

	@Test
	void flatGroundIsWalkableButNotADrop() {
		assertTrue(BorerFallPolicy.canWalk(0));
		assertFalse(BorerFallPolicy.shouldWalkIntoDrop(0));
		assertFalse(BorerFallPolicy.shouldBridge(0));
	}

	@Test
	void unsafeDropMustNotWalkAndMayBridge() {
		assertFalse(BorerFallPolicy.canWalk(-1));
		assertFalse(BorerFallPolicy.shouldWalkIntoDrop(-1));
		assertTrue(BorerFallPolicy.shouldBridge(-1));
	}

	@Test
	void noFallDeepDropIsWalkableNotBridged() {
		assertTrue(BorerFallPolicy.canWalk(10));
		assertTrue(BorerFallPolicy.shouldWalkIntoDrop(10));
		assertFalse(BorerFallPolicy.shouldBridge(10));
	}

	@Test
	void stalledMiningNextToSafeDropWalksIntoIt() {
		assertTrue(BorerFallPolicy.abandonMineAndWalkDrop(2, true));
		assertFalse(BorerFallPolicy.abandonMineAndWalkDrop(2, false));
		assertFalse(BorerFallPolicy.abandonMineAndWalkDrop(0, true));
		assertFalse(BorerFallPolicy.abandonMineAndWalkDrop(-1, true));
	}

	@Test
	void climbingToOreStillWalksOneBlockStep() {
		assertTrue(BorerFallPolicy.shouldWalkIntoDrop(1, true));
		assertTrue(BorerFallPolicy.shouldWalkIntoDrop(1, false));
		assertFalse(BorerFallPolicy.shouldWalkIntoDrop(2, true));
		assertFalse(BorerFallPolicy.shouldWalkIntoDrop(5, true));
		assertTrue(BorerFallPolicy.shouldWalkIntoDrop(5, false));
		assertFalse(BorerFallPolicy.shouldWalkIntoDrop(0, true));
		assertFalse(BorerFallPolicy.shouldWalkIntoDrop(-1, true));
	}

	@Test
	void climbingDropDoesNotIdleWhenOreIsInReach() {
		assertTrue(BorerFallPolicy.climbDropNeedsAscent(2, true));
		assertTrue(BorerFallPolicy.climbDropNeedsAscent(5, true));
		assertFalse(BorerFallPolicy.climbDropNeedsAscent(1, true));
		assertFalse(BorerFallPolicy.climbDropNeedsAscent(2, false));
		assertTrue(BorerFallPolicy.mineInReachInsteadOfWaitClimbDrop(true, true));
		assertFalse(BorerFallPolicy.mineInReachInsteadOfWaitClimbDrop(false, true));
		assertFalse(BorerFallPolicy.mineInReachInsteadOfWaitClimbDrop(true, false));
	}

	@Test
	void mustNotRestrictSafeWalkToExactlyOneBlock() {
		assertTrue(BorerFallPolicy.shouldWalkIntoDrop(2));
		assertTrue(BorerFallPolicy.canWalk(2));
		assertFalse(BorerFallPolicy.shouldBridge(2));
	}

	@Test
	void floorOreIsMinedWhenLandingAfterMineIsSafe() {
		assertTrue(BorerFallPolicy.canMineFloorIfLandingSafe(0));
		assertTrue(BorerFallPolicy.canMineFloorIfLandingSafe(1));
		assertTrue(BorerFallPolicy.canMineFloorIfLandingSafe(3));
		assertFalse(BorerFallPolicy.canMineFloorIfLandingSafe(-1));
	}

	@Test
	void stalledSafeDropMayBridgeOnlyAsALastResort() {
		assertFalse(BorerFallPolicy.shouldRecoverStalledSafeDrop(2, 39));
		assertTrue(BorerFallPolicy.shouldRecoverStalledSafeDrop(2, 40));
		assertFalse(BorerFallPolicy.shouldRecoverStalledSafeDrop(0, 80));
		assertFalse(BorerFallPolicy.shouldRecoverStalledSafeDrop(-1, 80));
		assertTrue(BorerFallPolicy.shouldBridgeStalledSafeDrop(2, 40, false, false));
		assertFalse(BorerFallPolicy.shouldBridgeStalledSafeDrop(2, 40, true, false));
		assertFalse(BorerFallPolicy.shouldBridgeStalledSafeDrop(2, 40, false, true));
	}

	@Test
	void areaFallRequiresAirBelowAndSafeLanding() {
		assertTrue(BorerFallPolicy.areaCanFall(true, 2));
		assertTrue(BorerFallPolicy.areaCanFall(true, 0));
		assertFalse(BorerFallPolicy.areaCanFall(false, 2));
		assertFalse(BorerFallPolicy.areaCanFall(true, -1));
	}
}
