package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.chopper.ChopperMinePolicy;

final class ChopperMinePolicyTest {
	@Test
	void shearsOnLeavesClickEveryTickAndKeepHeldThatTick() {
		assertTrue(ChopperMinePolicy.oneClickBreaks(1.0f));
		assertFalse(ChopperMinePolicy.oneClickBreaks(0.2f));
		assertTrue(ChopperMinePolicy.clickThisTick(false, false, true, false));
		assertTrue(ChopperMinePolicy.holdAttack(true, true));
		assertFalse(ChopperMinePolicy.holdAttack(true, false));
	}

	@Test
	void noProgressClicksAgain() {
		assertTrue(ChopperMinePolicy.clickThisTick(false, false, false, true));
		assertFalse(ChopperMinePolicy.clickThisTick(false, false, false, false));
		assertTrue(ChopperMinePolicy.holdAttack(false, false));
		assertTrue(ChopperMinePolicy.holdAttack(false, true));
	}
}
