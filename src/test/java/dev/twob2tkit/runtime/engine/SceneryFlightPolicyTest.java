package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SceneryFlightPolicyTest {
	@Test void holdsFortyEightBlocksAboveMountainsAndDoesNotDescendBetweenPeaks() {
		assertEquals(160, SceneryFlightPolicy.altitude(64, 65, 0));
		assertEquals(348, SceneryFlightPolicy.altitude(160, 300, 160));
		assertEquals(348, SceneryFlightPolicy.altitude(348, 64, 348));
	}
	@Test void risesBeforeForwardTravelAndKeepsHorizontalAndVerticalInputsExclusive() {
		var up = SceneryFlightPolicy.input(200, 200, 100, 0, 90);
		assertTrue(up.up()); assertFalse(up.forward());
		var coast = SceneryFlightPolicy.input(200, 0, .5, .5, 0); assertFalse(coast.forward());
		var go = SceneryFlightPolicy.input(200, 0, 0, 0, 0); assertTrue(go.forward()); assertEquals(-90, go.yaw()); assertFalse(go.up());
		assertTrue(go.speed() * 15 < 1.5); assertTrue(up.speed() * 5 < 1.2);
	}
	@Test void realInputMappingCrossesMountainOnlyAfterGainingRequiredHeight() {
		double x = 0, y = 65, altitude = 160, vy = 0; boolean passed = false;
		for (int tick = 0; tick < 2000 && x < 198.5; tick++) {
			int ahead = x + 12 >= 80 && x <= 130 ? 300 : 65;
			altitude = SceneryFlightPolicy.altitude(y, ahead, altitude);
			var input = SceneryFlightPolicy.input(200 - x, 0, altitude - y, vy, -90);
			vy = input.up() ? input.speed() * 5 : 0; y += vy;
			if (input.forward()) x += input.speed() * 15;
			if (x >= 80 && x <= 130) { passed = true; assertTrue(y >= 347); }
		}
		assertTrue(passed); assertTrue(x >= 198.5);
	}
}
