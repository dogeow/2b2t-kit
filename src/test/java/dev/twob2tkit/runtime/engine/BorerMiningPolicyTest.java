package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 锁住真实准星授权、普通遮挡排除和脚下支撑矿保护。 */
final class BorerMiningPolicyTest {
	@Test
	void attackRequiresARealHitOnTheExpectedTargetWithinReach() {
		Object expected = "382834,84,311127";

		assertTrue(BorerMiningPolicy.allowAttack(expected, expected, true));
		assertFalse(BorerMiningPolicy.allowAttack(expected, expected, false));
		assertFalse(BorerMiningPolicy.allowAttack(expected, "382836,82,311127", true));
	}

	@Test
	void missingOrSyntheticHitCannotAuthorizeAttack() {
		Object expected = "target";

		assertFalse(BorerMiningPolicy.allowAttack(expected, null, true));
		assertFalse(BorerMiningPolicy.allowAttack(null, expected, true));
		assertFalse(BorerMiningPolicy.allowAttack(null, null, true));
	}

	@Test
	void onlyTimedOutOrdinaryObstructionsAreSuppressed() {
		assertTrue(BorerMiningPolicy.shouldSuppressRetry(false, true));
		assertFalse(BorerMiningPolicy.shouldSuppressRetry(true, true));
		assertFalse(BorerMiningPolicy.shouldSuppressRetry(false, false));
		assertFalse(BorerMiningPolicy.shouldSuppressRetry(true, false));
	}

	@Test
	void aimMissWalksWhenFloorIsSafeEvenIfTargetWasAlreadyInRange() {
		assertTrue(BorerMiningPolicy.shouldWalkAfterAimMiss(true));
		assertFalse(BorerMiningPolicy.shouldWalkAfterAimMiss(false));
	}

	@Test
	void inReachOreMinesTheRealHitInsteadOfReplanning() {
		assertTrue(BorerMiningPolicy.mineRealHitTowardInReachOre(true, false, true));
		assertFalse(BorerMiningPolicy.mineRealHitTowardInReachOre(true, true, true));
		assertFalse(BorerMiningPolicy.mineRealHitTowardInReachOre(true, false, false));
		assertFalse(BorerMiningPolicy.mineRealHitTowardInReachOre(false, false, true));
	}

	@Test
	void inReachOreUsesVisibleFaceWhenAxisAimMisses() {
		assertTrue(BorerMiningPolicy.useVisibleFaceWhenAxisMisses(true, false, true));
		assertFalse(BorerMiningPolicy.useVisibleFaceWhenAxisMisses(true, true, true));
		assertFalse(BorerMiningPolicy.useVisibleFaceWhenAxisMisses(true, false, false));
		assertFalse(BorerMiningPolicy.useVisibleFaceWhenAxisMisses(false, false, true));
	}

	@Test
	void adjacentOreMinesTheHeadFirstWhenBothCellsAreSolid() {
		assertTrue(BorerMiningPolicy.mineHeadToSeeAdjacentOre(true, true));
		assertFalse(BorerMiningPolicy.mineHeadToSeeAdjacentOre(true, false));
		assertFalse(BorerMiningPolicy.mineHeadToSeeAdjacentOre(false, true));
		assertFalse(BorerMiningPolicy.mineHeadToSeeAdjacentOre(false, false));
	}

	@Test
	void sideCornerBlockingThePlayerIsMinedInsteadOfDiscarded() {
		assertFalse(BorerMiningPolicy.rejectAsSideWall(true, true));
		assertTrue(BorerMiningPolicy.rejectAsSideWall(true, false));
		assertFalse(BorerMiningPolicy.rejectAsSideWall(false, false));
	}

	@Test
	void suppressedBlockCannotBeSelectedAgainOnTheNextTick() {
		long now = 1_000L;
		long until = now + 60L;
		assertTrue(BorerMiningPolicy.suppressionActive(now + 1L, until));
		assertFalse(BorerMiningPolicy.canSelectTarget(true,
			BorerMiningPolicy.suppressionActive(now + 1L, until)));
		assertFalse(BorerMiningPolicy.suppressionActive(until, until));
		assertTrue(BorerMiningPolicy.canSelectTarget(true,
			BorerMiningPolicy.suppressionActive(until, until)));
		assertFalse(BorerMiningPolicy.canSelectTarget(false, false));
	}

	@Test
	void standingSupportOreIsMinedWhenLandingIsSafe() {
		assertTrue(BorerMiningPolicy.adjacentOreCanBeSelected(0, -1, true, true));
		assertFalse(BorerMiningPolicy.adjacentOreCanBeSelected(0, -1, true, false));
		assertTrue(BorerMiningPolicy.adjacentOreCanBeSelected(0, -1, false, true));
	}

	@Test
	void otherAdjacentOreStillFollowsOrePolicy() {
		assertTrue(BorerMiningPolicy.adjacentOreCanBeSelected(1, -1, true, true));
		assertFalse(BorerMiningPolicy.adjacentOreCanBeSelected(1, -1, false, false));
		assertTrue(BorerMiningPolicy.adjacentOreCanBeSelected(0, 0, false, false));
		assertTrue(BorerMiningPolicy.adjacentOreCanBeSelected(1, 2, false, false));
		assertFalse(BorerMiningPolicy.adjacentOreCanBeSelected(1, -2, false, true));
		assertFalse(BorerMiningPolicy.adjacentOreCanBeSelected(2, 0, false, true));
	}
}
