package dev.twob2tkit.cruise;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CruiseHudStateTest {
	private static final long TWO_SECONDS = 2_000_000_000L;

	@Test
	void phaseNoticeTakesPriorityThenReturnsToOneLineProgress() {
		CruiseHudState state = new CruiseHudState();
		state.begin("巡航 · 调整高度 Y 70→90");
		state.notice("已到 Y 90 · 开始前进", 1_000L, TWO_SECONDS);
		state.status("巡航 · 前进 · 剩余 28 格");
		assertEquals("已到 Y 90 · 开始前进", state.line(1_000L + TWO_SECONDS - 1));
		assertTrue(state.showingNotice(1_000L + TWO_SECONDS - 1));
		assertEquals("巡航 · 前进 · 剩余 28 格", state.line(1_000L + TWO_SECONDS));
		assertFalse(state.showingNotice(1_000L + TWO_SECONDS));
	}

	@Test
	void arrivalDisappearsAfterTwoSecondsWithoutAnotherTick() {
		CruiseHudState state = new CruiseHudState();
		state.begin("巡航 · 前进 · 剩余 4 格");
		state.finish("已到达目标", 5_000L, TWO_SECONDS);
		assertEquals("已到达目标", state.line(5_000L + TWO_SECONDS - 1));
		assertEquals("", state.line(5_000L + TWO_SECONDS));
	}

	@Test
	void nextShortNavigationClearsPreviousArrivalImmediately() {
		CruiseHudState state = new CruiseHudState();
		state.finish("已到达目标", 1_000L, TWO_SECONDS);
		state.begin("巡航 · 调整高度至 Y 96");
		assertEquals("巡航 · 调整高度至 Y 96", state.line(1_001L));
		state.clear();
		assertEquals("", state.line(1_002L));
	}
}
