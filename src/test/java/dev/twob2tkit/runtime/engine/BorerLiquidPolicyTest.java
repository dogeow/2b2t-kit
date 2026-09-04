package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

final class BorerLiquidPolicyTest {
	@Test
	void oneBlockDripIsALeakLakeIsSkipped() {
		assertTrue(BorerLiquidPolicy.isSmallLeak(1, 4));
		assertTrue(BorerLiquidPolicy.isSmallLeak(0, 1));
		assertFalse(BorerLiquidPolicy.isSmallLeak(1, 0));
		assertFalse(BorerLiquidPolicy.isSmallLeak(3, 2));
		assertTrue(BorerLiquidPolicy.isLake(3));
		assertFalse(BorerLiquidPolicy.isLake(2));
		assertTrue(BorerLiquidPolicy.skipShaftForLake(true, 4));
		assertFalse(BorerLiquidPolicy.skipShaftForLake(false, 4));
		assertTrue(BorerLiquidPolicy.ignoreLakeCandidate(true, 5));
		assertFalse(BorerLiquidPolicy.ignoreLakeCandidate(true, 1));
	}

	@Test
	void walkOverToPlugAFarLeakAndGiveUpAfterRetries() {
		assertTrue(BorerLiquidPolicy.shouldWalkToLeak(true, false, 1.0));
		assertTrue(BorerLiquidPolicy.shouldWalkToLeak(true, true, 4.0));
		assertFalse(BorerLiquidPolicy.shouldWalkToLeak(true, true, 1.0));
		assertFalse(BorerLiquidPolicy.shouldWalkToLeak(false, false, 9.0));
		assertFalse(BorerLiquidPolicy.giveUpAfterFails(2));
		assertTrue(BorerLiquidPolicy.giveUpAfterFails(3));
		assertEquals(6, BorerLiquidPolicy.settleTicks(true, true));
		assertEquals(0, BorerLiquidPolicy.settleTicks(false, true));
		assertEquals(4, BorerLiquidPolicy.settleTicks(false, false));
	}
}
