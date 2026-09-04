package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.chopper.ChopperLootPolicy;

final class ChopperLootPolicyTest {
	@Test
	void closeEnoughUsesHorizontalReach() {
		assertTrue(ChopperLootPolicy.closeEnoughForPickup(0.8, 1.0, 1.29));
		assertFalse(ChopperLootPolicy.closeEnoughForPickup(1.4, 0.2, 1.42));
	}

	@Test
	void oscillatingDistanceDoesNotResetStuckForever() {
		assertFalse(ChopperLootPolicy.progressResetsStuck(1.0, 1.35));
		assertTrue(ChopperLootPolicy.progressResetsStuck(0.7, 1.35));
	}

	@Test
	void groundLootBelowPlayerLandsInsteadOfKeepingFlight() {
		assertFalse(ChopperLootPolicy.keepFlightForLockedTarget(true, -1.0, true));
		assertTrue(ChopperLootPolicy.keepFlightForLockedTarget(true, 2.0, true));
	}

	@Test
	void closeRangeStopsWalkingForward() {
		assertFalse(ChopperLootPolicy.shouldWalkForward(0.8, 1.0, 1.29, true));
		assertTrue(ChopperLootPolicy.shouldWalkForward(1.4, 0.2, 1.42, false));
	}
}
