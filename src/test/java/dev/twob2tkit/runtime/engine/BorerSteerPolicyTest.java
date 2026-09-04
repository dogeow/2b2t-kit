package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class BorerSteerPolicyTest {
	@Test
	void pressesTowardRemainingError() {
		assertFalse(BorerSteerPolicy.needMove(0.06, 0.06));
		assertTrue(BorerSteerPolicy.needMove(0.09, 0.01));
		assertTrue(BorerSteerPolicy.pressPositive(0.20, 0.30, true));
		assertTrue(BorerSteerPolicy.pressNegative(-0.20, -0.30, true));
		assertFalse(BorerSteerPolicy.pressPositive(0.04, 0.20, true));
		assertFalse(BorerSteerPolicy.pressNegative(0.04, 0.20, true));
	}

	@Test
	void reversesWhenErrorGrowsAndStopsWhenCrossingCenter() {
		assertTrue(BorerSteerPolicy.errorGrew(0.15, 0.22));
		assertTrue(BorerSteerPolicy.pressNegative(0.22, 0.15, true));
		assertTrue(BorerSteerPolicy.crossed(0.10, -0.05));
		assertFalse(BorerSteerPolicy.pressPositive(-0.05, 0.10, true));
		assertFalse(BorerSteerPolicy.pressNegative(-0.05, 0.10, true));
	}

	@Test
	void brakesWhenDistanceIncreasesAndSlowsFastFlight() {
		assertTrue(BorerSteerPolicy.shouldBrake(0.20, 0.28, true));
		assertFalse(BorerSteerPolicy.shouldBrake(0.28, 0.20, true));
		assertTrue(BorerSteerPolicy.shouldSlowFlight(0.10));
		assertFalse(BorerSteerPolicy.shouldSlowFlight(0.03));
	}
}
