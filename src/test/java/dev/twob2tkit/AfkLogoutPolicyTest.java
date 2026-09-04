package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 锁住：附近有骷髅不够，被打中一次才下线。
 * 来源：2026-08-22 「就算有骷髅，没有被攻击过一次也不要下线，它只是在旁边」。
 */
final class AfkLogoutPolicyTest {
	@Test
	void nearbySkeletonDoesNotLogOutUntilHit() {
		assertFalse(AfkLogoutPolicy.watchNearbyHostiles(true));
		assertFalse(AfkLogoutPolicy.nearbyHostileLogsOut(true, false));
		assertTrue(AfkLogoutPolicy.hitLogsOut(true));
	}

	@Test
	void nearbyMeleeDrownedDoesNotLogOutUntilHit() {
		assertFalse(AfkLogoutPolicy.nearbyHostileLogsOut(true, true));
		assertTrue(AfkLogoutPolicy.hitLogsOut(true));
	}

	@Test
	void feedingOrIdleDoesNotLogOutForNearbyOrHit() {
		assertFalse(AfkLogoutPolicy.watchNearbyHostiles(false));
		assertFalse(AfkLogoutPolicy.nearbyHostileLogsOut(false, false));
		assertFalse(AfkLogoutPolicy.hitLogsOut(false));
	}
}
