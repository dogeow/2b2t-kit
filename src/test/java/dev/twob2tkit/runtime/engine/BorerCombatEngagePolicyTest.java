package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 贴近 / 举盾 / 远程怪识别规则。 */
final class BorerCombatEngagePolicyTest {
	@Test
	void hoverAboveMobHeadByDefault() {
		assertEquals(6.9, BorerCombatEngagePolicy.hoverFeetY(3.0, 1.9, 2.0), 0.01);
	}

	@Test
	void samePlaneWhenHeadroomBlocked() {
		assertEquals(3.0, BorerCombatEngagePolicy.resolveHoverFeetY(3.0, 1.9, 2.0, true), 0.01);
		assertEquals(6.9, BorerCombatEngagePolicy.resolveHoverFeetY(3.0, 1.9, 2.0, false), 0.01);
	}

	@Test
	void altitudeAdjustments() {
		assertTrue(BorerCombatEngagePolicy.shouldAscend(4.0, 6.9));
		assertFalse(BorerCombatEngagePolicy.shouldAscend(6.7, 6.9));
		assertTrue(BorerCombatEngagePolicy.shouldDescend(8.0, 6.9));
	}

	@Test
	void needsCloserOutsideMeleeReach() {
		assertTrue(BorerCombatEngagePolicy.needsCloser(6.0));
		assertFalse(BorerCombatEngagePolicy.needsCloser(3.5));
		assertFalse(BorerCombatEngagePolicy.needsCloser(2.0));
	}

	@Test
	void rangedTypeIds() {
		assertTrue(BorerThreats.isRangedCombatType("skeleton"));
		assertTrue(BorerThreats.isRangedCombatType("stray"));
		assertTrue(BorerThreats.isRangedCombatType("bogged"));
		assertTrue(BorerThreats.isRangedCombatType("pillager"));
		assertFalse(BorerThreats.isRangedCombatType("zombie"));
		assertFalse(BorerThreats.isRangedCombatType("creeper"));
	}

	@Test
	void wallHiddenMobIsNotEngageable() {
		assertFalse(BorerCombatEngagePolicy.canEngageThreat(false));
		assertTrue(BorerCombatEngagePolicy.canEngageThreat(true));
	}
}
