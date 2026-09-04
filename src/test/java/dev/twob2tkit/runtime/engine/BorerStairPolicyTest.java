package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：矿在更低处、前方是平地时要挖台阶，不要「向下挖阶梯」空走。
 * 来源：2026-08-18 樱花林地表，人在 y=119，绿宝石在 y=114，前方是花和草。
 */
final class BorerStairPolicyTest {
	@Test
	void flatGroundCutsAStairInsteadOfWalking() {
		assertTrue(BorerStairPolicy.shouldCutFloor(0));
		assertFalse(BorerStairPolicy.shouldWalkDown(0));
	}

	@Test
	void existingDropIsWalkedNotMined() {
		assertFalse(BorerStairPolicy.shouldCutFloor(1));
		assertTrue(BorerStairPolicy.shouldWalkDown(1));
		assertFalse(BorerStairPolicy.shouldCutFloor(3));
		assertTrue(BorerStairPolicy.shouldWalkDown(3));
	}

	@Test
	void unsafeDropIsNeitherCutNorWalked() {
		assertFalse(BorerStairPolicy.shouldCutFloor(-1));
		assertFalse(BorerStairPolicy.shouldWalkDown(-1));
	}

	@Test
	void adjacentFloorIsTheStairCut() {
		assertTrue(BorerStairPolicy.isCutFloor(1, -1));
		assertFalse(BorerStairPolicy.isCutFloor(0, -1));
		assertFalse(BorerStairPolicy.isCutFloor(1, 0));
		assertFalse(BorerStairPolicy.isCutFloor(2, -1));
	}

	@Test
	void emptyFeetAndSolidHeadMinesHeadToOpenOneByTwo() {
		assertTrue(BorerStairPolicy.mineHeadToOpenOneByTwo(true, true));
		assertFalse(BorerStairPolicy.mineHeadToOpenOneByTwo(true, false));
		assertFalse(BorerStairPolicy.mineHeadToOpenOneByTwo(false, true));
		assertFalse(BorerStairPolicy.mineHeadToOpenOneByTwo(false, false));
	}

	@Test
	void nextColumnGravelAboveCorridorIsIgnored() {
		assertTrue(BorerStairPolicy.ignoreOverheadFalling(1, 3, 2));
		assertFalse(BorerStairPolicy.ignoreOverheadFalling(0, 3, 2));
		assertFalse(BorerStairPolicy.ignoreOverheadFalling(1, 1, 2));
	}

	@Test
	void inReachKeepsAimInsteadOfWalkingCloser() {
		assertTrue(BorerStairPolicy.keepAimingInsteadOfWalking(true, true));
		assertFalse(BorerStairPolicy.keepAimingInsteadOfWalking(false, true));
		assertFalse(BorerStairPolicy.keepAimingInsteadOfWalking(true, false));
	}

	@Test
	void oneByTwoPrefersOreHeadingUntilInTheOreColumn() {
		assertTrue(BorerStairPolicy.tryOreHeadingFirst(2));
		assertFalse(BorerStairPolicy.tryOreHeadingFirst(0));
	}

	@Test
	void floorLayerOreIsNotAStairRoute() {
		assertFalse(BorerStairPolicy.needsVerticalRoute(-1));
		assertFalse(BorerStairPolicy.needsVerticalRoute(0));
		assertFalse(BorerStairPolicy.needsVerticalRoute(2));
		assertTrue(BorerStairPolicy.needsVerticalRoute(-2));
		assertTrue(BorerStairPolicy.needsVerticalRoute(3));
	}

	@Test
	void oneBlockDropWalksInsteadOfStallingDescend() {
		assertTrue(BorerStairPolicy.shouldWalkWhileDescending(0));
		assertTrue(BorerStairPolicy.shouldWalkWhileDescending(1));
		assertTrue(BorerStairPolicy.shouldWalkWhileDescending(3));
		assertFalse(BorerStairPolicy.shouldWalkWhileDescending(-1));
	}

	@Test
	void meteorStepWalksUpOneBlockWhenHeadroomIsClear() {
		assertTrue(BorerStairPolicy.walkUpOneBlockStep(true, true, true, true));
		assertFalse(BorerStairPolicy.walkUpOneBlockStep(false, true, true, true));
		assertFalse(BorerStairPolicy.walkUpOneBlockStep(true, false, true, true));
		assertFalse(BorerStairPolicy.walkUpOneBlockStep(true, true, false, true));
	}

	@Test
	void lowerOreMinesFrontWallInsteadOfWaitingNoSight() {
		assertFalse(BorerStairPolicy.walkUpOneBlockStep(true, true, true, false));
		assertFalse(BorerStairPolicy.occludeWhenFrontBlocked(true, true));
		assertTrue(BorerStairPolicy.occludeWhenFrontBlocked(true, false));
		assertFalse(BorerStairPolicy.occludeWhenFrontBlocked(false, true));
	}
}
