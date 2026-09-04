package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.combat.AutoProtectPolicy;

/** 锁住：被怪物打了才开 Meteor 杀戮和自动断开；岩浆烫伤不开。 */
final class AutoProtectPolicyTest {
	@Test
	void mobHitArmsWhenEnabled() {
		assertTrue(AutoProtectPolicy.armOnMobHit(true, true));
		assertFalse(AutoProtectPolicy.armOnMobHit(true, false));
		assertFalse(AutoProtectPolicy.armOnMobHit(false, true));
	}
}
