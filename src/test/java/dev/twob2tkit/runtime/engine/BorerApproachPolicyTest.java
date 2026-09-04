package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class BorerApproachPolicyTest {
	@Test
	void outOfReachFliesToTheBlockNotAlongTheCorridor() {
		assertTrue(BorerApproachPolicy.approachTargetInsteadOfCorridor(false));
		assertFalse(BorerApproachPolicy.approachTargetInsteadOfCorridor(true));
		assertTrue(BorerApproachPolicy.holdForward(1.0));
		assertFalse(BorerApproachPolicy.holdForward(0.2));
		assertTrue(BorerApproachPolicy.descend(53.0, 56.4));
		assertFalse(BorerApproachPolicy.descend(56.0, 56.4));
		assertTrue(BorerApproachPolicy.ascend(62.0, 56.4));
		assertTrue(BorerApproachPolicy.enableFlight(true, 53.0, 56.4));
		assertTrue(BorerApproachPolicy.enableFlight(false, 53.0, 56.4));
		assertFalse(BorerApproachPolicy.enableFlight(false, 56.0, 56.4));
		assertTrue(BorerApproachPolicy.dropDownSameColumn(true, true));
		assertFalse(BorerApproachPolicy.dropDownSameColumn(false, true));
		assertFalse(BorerApproachPolicy.dropDownSameColumn(true, false));
		assertFalse(BorerApproachPolicy.walkCorridorWhenTooFar(true));
		assertTrue(BorerApproachPolicy.walkCorridorWhenTooFar(false));
	}
}
