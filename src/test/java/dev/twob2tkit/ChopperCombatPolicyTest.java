package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.chopper.ChopperCombatPolicy;

final class ChopperCombatPolicyTest {
	@Test
	void ironGolemIsAThreatEvenThoughNotEnemy() {
		assertTrue(ChopperCombatPolicy.isThreatType(false, "iron_golem"));
		assertTrue(ChopperCombatPolicy.isNeutralGolem("iron_golem"));
		assertFalse(ChopperCombatPolicy.isNeutralGolem("zombie"));
		assertTrue(ChopperCombatPolicy.isThreatType(true, "zombie"));
		assertFalse(ChopperCombatPolicy.isThreatType(false, "cow"));
		assertFalse(ChopperCombatPolicy.isThreatType(false, "snow_golem"));
	}

	@Test
	void peacefulGolemIgnoredWhenKillAuraOff() {
		assertFalse(ChopperCombatPolicy.shouldEngageNeutral(false, false));
	}

	@Test
	void golemEngagedWhenKillAuraOnOrTargetingPlayer() {
		assertTrue(ChopperCombatPolicy.shouldEngageNeutral(true, false));
		assertTrue(ChopperCombatPolicy.shouldEngageNeutral(false, true));
		assertTrue(ChopperCombatPolicy.shouldEngageNeutral(true, true));
	}

	@Test
	void pauseWhenHurtOrThreatNearby() {
		assertTrue(ChopperCombatPolicy.shouldPause(true, false));
		assertTrue(ChopperCombatPolicy.shouldPause(false, true));
		assertFalse(ChopperCombatPolicy.shouldPause(false, false));
	}
}
