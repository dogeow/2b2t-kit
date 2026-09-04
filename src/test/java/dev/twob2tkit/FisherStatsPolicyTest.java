package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.fisher.FisherStatsPolicy;

/** 锁住钓鱼字幕：只报条数和平均间隔，不报等咬钩。 */
final class FisherStatsPolicyTest {
	@Test
	void noCatchYetShowsDashAverage() {
		assertEquals("0条  已钓 1:23  平均 —", FisherStatsPolicy.hud(0, 83_000L));
	}

	@Test
	void averageIsSessionTimeDividedByCatches() {
		String line = FisherStatsPolicy.hud(4, 120_000L);
		assertTrue(line.contains("4条"));
		assertTrue(line.contains("平均 30秒/条"));
		assertTrue(line.contains("已钓 2:00"));
	}

	@Test
	void minutesAreUsedWhenACatchTakesLongerThanAMinute() {
		assertEquals("1分30秒", FisherStatsPolicy.formatSeconds(90.0));
		assertEquals("1:05:00", FisherStatsPolicy.formatDuration(3_900_000L));
	}
}
