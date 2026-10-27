package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.chopper.ChopperCombatPolicy;

final class ChopperCombatPolicyTest {
	@Test
	void hostileMobsRetainTheExistingPauseAndOtherNeutralAnimalsStayIgnored() {
		assertTrue(ChopperCombatPolicy.isThreat(true, false, false, false, false));
		assertFalse(ChopperCombatPolicy.isThreat(false, false, false, false, false));
		assertFalse(ChopperCombatPolicy.isThreat(false, false, true, true, true));
	}

	@Test
	void peacefulGolemIsIgnoredWithoutEvidenceOfEngagement() {
		assertFalse(ChopperCombatPolicy.isThreat(false, true, false, false, false));
	}

	@Test
	void golemPausesChoppingOnlyWhenTargetingAttackingOrActuallySelectedByAura() {
		assertTrue(ChopperCombatPolicy.isThreat(false, true, true, false, false));
		assertTrue(ChopperCombatPolicy.isThreat(false, true, false, true, false));
		assertTrue(ChopperCombatPolicy.isThreat(false, true, false, false, true));
	}

	@Test
	void recentAttackEvidenceExpiresAndRejectsAnInvalidAge() {
		assertTrue(ChopperCombatPolicy.recentAttacker(true, 0));
		assertTrue(ChopperCombatPolicy.recentAttacker(true, 100));
		assertFalse(ChopperCombatPolicy.recentAttacker(true, 101));
		assertFalse(ChopperCombatPolicy.recentAttacker(true, -1));
		assertFalse(ChopperCombatPolicy.recentAttacker(false, 0));
	}

	@Test
	void pauseWhenHurtOrThreatNearby() {
		assertTrue(ChopperCombatPolicy.shouldPause(true, false));
		assertTrue(ChopperCombatPolicy.shouldPause(false, true));
		assertFalse(ChopperCombatPolicy.shouldPause(false, false));
	}
}
