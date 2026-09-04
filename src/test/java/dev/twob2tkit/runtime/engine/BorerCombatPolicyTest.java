package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：岩浆块烫伤不要提示被骷髅打。lastHurtByMob 会残留。
 */
final class BorerCombatPolicyTest {
	@Test
	void magmaBurnIsNotASkeletonHit() {
		assertFalse(BorerCombatPolicy.treatAsMobHit(true, true, 2));
		assertFalse(BorerCombatPolicy.treatAsMobHit(true, true, 200));
		assertFalse(BorerCombatPolicy.pauseMiningForCombat(false));
		assertEquals("岩浆块", BorerCombatPolicy.hurtCauseLabel(true, "岩浆块", "骷髅", false));
	}

	@Test
	void recentMobHitStillCounts() {
		assertTrue(BorerCombatPolicy.treatAsMobHit(true, false, 0));
		assertTrue(BorerCombatPolicy.treatAsMobHit(true, false, 10));
		assertFalse(BorerCombatPolicy.treatAsMobHit(true, false, 80));
		assertFalse(BorerCombatPolicy.treatAsMobHit(false, false, 2));
		assertEquals("骷髅", BorerCombatPolicy.hurtCauseLabel(false, "岩浆块", "骷髅", true));
		assertNull(BorerCombatPolicy.hurtCauseLabel(false, null, "骷髅", false));
	}
}
