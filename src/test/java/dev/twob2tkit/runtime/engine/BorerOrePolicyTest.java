package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：矿在身旁一格、通道已通时要挖矿，不要「没有可挖视线」原地等。
 * 来源：2026-08-18 绿宝石在 382733 111，人在 382732 112，前方 1×2 已是空气。
 */
final class BorerOrePolicyTest {
	@Test
	void adjacentOreOneBlockDownIsMinedNotWaited() {
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfWait(1, -1));
		assertTrue(BorerOrePolicy.waitWouldSkipAdjacentOre(1, -1, true));
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfHold(1, -1, true));
	}

	@Test
	void openCorridorDoesNotIdleWhenFloorOreIsBesideTheFeet() {
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfHold(1, -1, true));
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfHold(0, -1, true));
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfHold(1, -1, false));
		assertFalse(BorerOrePolicy.mineAdjacentInsteadOfHold(2, -1, true));
	}

	@Test
	void blockedCorridorStillMinesTheOreUnderfoot() {
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfHold(1, -1, false));
		assertTrue(BorerOrePolicy.mineAdjacentOre(1, -1, false, true));
		assertTrue(BorerOrePolicy.mineAdjacentOre(0, -1, true, true));
		assertFalse(BorerOrePolicy.mineAdjacentOre(0, -1, true, false));
		assertFalse(BorerOrePolicy.mineAdjacentOre(1, -1, false, false));
	}

	@Test
	void sameLevelOreDoesNotNeedASafeLanding() {
		assertTrue(BorerOrePolicy.mineAdjacentOre(1, 0, false, false));
		assertTrue(BorerOrePolicy.mineAdjacentOre(1, 2, false, false));
	}

	@Test
	void adjacentSameLevelOreIsMined() {
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfWait(1, 0));
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfWait(1, 1));
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfWait(0, 0));
	}

	@Test
	void farOreStillNeedsATunnel() {
		assertFalse(BorerOrePolicy.mineAdjacentInsteadOfWait(2, -1));
		assertFalse(BorerOrePolicy.waitWouldSkipAdjacentOre(2, 0, true));
	}

	@Test
	void twoBlocksBelowNeedsVerticalRouteNotThisShortcut() {
		assertFalse(BorerOrePolicy.mineAdjacentInsteadOfWait(1, -2));
	}

	@Test
	void ceilingOreAboveHeadIsMinedNotTunneled() {
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfWait(0, 2));
		assertTrue(BorerOrePolicy.mineAdjacentInsteadOfWait(1, 2));
		assertTrue(BorerOrePolicy.waitWouldSkipAdjacentOre(0, 2, true));
	}

	@Test
	void underfootAndAdjacentBeatDistantSameLevel() {
		double underfoot = BorerOrePolicy.approachScore(0, 0, -1);
		double adjacent = BorerOrePolicy.approachScore(1, 0, 0);
		double adjacentFloor = BorerOrePolicy.approachScore(1, 0, -1);
		double fourAway = BorerOrePolicy.approachScore(4, 0, 0);
		double eightAway = BorerOrePolicy.approachScore(8, 0, 0);
		assertTrue(underfoot < fourAway);
		assertTrue(adjacent < fourAway);
		assertTrue(adjacentFloor < fourAway);
		assertTrue(underfoot < eightAway);
		assertTrue(BorerOrePolicy.preferNewOre(underfoot, eightAway));
		assertFalse(BorerOrePolicy.preferNewOre(eightAway, underfoot));
	}

	@Test
	void nearbyBeatsFarOnTheSameLayer() {
		assertTrue(BorerOrePolicy.approachScore(2, 0, 0) < BorerOrePolicy.approachScore(10, 0, 0));
		assertTrue(BorerOrePolicy.approachScore(1, 1, 0) < BorerOrePolicy.approachScore(6, 0, 0));
	}
}
