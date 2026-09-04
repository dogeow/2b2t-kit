package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：挖矿时旁边有怪要停手，不要等贴身 2.8 格；关了「遇怪躲开」才继续挖。
 */
final class BorerMobPolicyTest {
	@Test
	void pauseUsesConfiguredRadiusNotMeleeOnly() {
		assertEquals(8.0, BorerMobPolicy.pauseRadius(8));
		assertEquals(2.0, BorerMobPolicy.pauseRadius(0));
		assertEquals(24.0, BorerMobPolicy.pauseRadius(99));
		assertTrue(BorerMobPolicy.pauseRadius(8) > 2.8);
	}

	@Test
	void nearbyHostilePausesWhenEnabled() {
		assertTrue(BorerMobPolicy.pauseMiningForNearby(true, true));
		assertFalse(BorerMobPolicy.pauseMiningForNearby(true, false));
		assertFalse(BorerMobPolicy.pauseMiningForNearby(false, true));
	}
}
