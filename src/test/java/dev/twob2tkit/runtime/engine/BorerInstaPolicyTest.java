package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 锁住秒破石头：点一下换下一块，不要按住同一格空等。 */
final class BorerInstaPolicyTest {
	@Test
	void onePunchStoneClicksThenReleases() {
		assertTrue(BorerInstaPolicy.oneClickBreaks(1.0f));
		assertTrue(BorerInstaPolicy.oneClickBreaks(1.2f));
		assertFalse(BorerInstaPolicy.oneClickBreaks(0.99f));
		assertFalse(BorerInstaPolicy.holdAttack(true));
		assertTrue(BorerInstaPolicy.holdAttack(false));
	}

	@Test
	void instaSkipServerConfirmHardBlocksStillWait() {
		assertEquals(0, BorerInstaPolicy.clearConfirmTicks(true, 3));
		assertEquals(3, BorerInstaPolicy.clearConfirmTicks(false, 3));
	}

	@Test
	void instaClicksEveryTickUntilGone() {
		assertTrue(BorerInstaPolicy.clickThisTick(false, false, true));
		assertTrue(BorerInstaPolicy.clickThisTick(true, false, false));
		assertTrue(BorerInstaPolicy.clickThisTick(false, true, false));
		assertFalse(BorerInstaPolicy.clickThisTick(false, false, false));
	}
}
