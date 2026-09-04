package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.logreview.LogReviewPolicy;

final class LogReviewPolicyTest {
	@Test
	void stallAndStandStillAreUrgent() {
		assertTrue(LogReviewPolicy.urgent("stall skip=1\nstall skip=2\n"));
		assertTrue(LogReviewPolicy.urgent("stand-skip dest=1,2,3\n"));
		assertTrue(LogReviewPolicy.urgent("status=够得着，停住砍 橡木原木\n"));
		assertTrue(LogReviewPolicy.urgent("shears-worn using-fist\n"));
		assertTrue(LogReviewPolicy.urgent("approach-stuck dest=1\n"));
		assertTrue(LogReviewPolicy.urgent("harvest-stall crop=1,2,3\n"));
		assertTrue(LogReviewPolicy.urgent("unstick round=1 player=1,2,3\n"));
		assertTrue(LogReviewPolicy.urgent("no-block missing=3\n"));
		assertTrue(LogReviewPolicy.urgent("cannot-break target=1,2,3\n"));
		assertTrue(LogReviewPolicy.urgent("no-rod player=1,2,3\n"));
		assertTrue(LogReviewPolicy.urgent("pearl-fail throws=8\n"));
		assertTrue(LogReviewPolicy.urgent("place-fail pos=1,2,3\n"));
		assertTrue(LogReviewPolicy.urgent("death killer=僵尸 piglin msg=被僵尸杀死\n"));
		assertTrue(LogReviewPolicy.urgent("inventory-full chest=-\n"));
		assertFalse(LogReviewPolicy.urgent("periodic action=MINE status=砍 橡木原木\n"));
		assertFalse(LogReviewPolicy.urgent("periodic status=已围好 10/10\n"));
		assertFalse(LogReviewPolicy.urgent("out-of-reach missing=3\n"));
		assertFalse(LogReviewPolicy.urgent(""));
	}

	@Test
	void hostModulesAreReviewableExceptBorer() {
		assertTrue(LogReviewPolicy.reviewable("chopper"));
		assertTrue(LogReviewPolicy.reviewable("surround"));
		assertTrue(LogReviewPolicy.reviewable("builder"));
		assertFalse(LogReviewPolicy.reviewable("borer"));
		assertEquals("挖树", LogReviewPolicy.label("chopper"));
		assertEquals("围箱", LogReviewPolicy.label("surround"));
		assertEquals("建造", LogReviewPolicy.label("builder"));
	}

	@Test
	void clipMissFloodIsUrgent() {
		StringBuilder chunk = new StringBuilder();
		for (int i = 0; i < 8; i++) chunk.append("clip-miss target=").append(i).append('\n');
		assertTrue(LogReviewPolicy.urgent(chunk.toString()));
		assertFalse(LogReviewPolicy.urgent("clip-miss target=1\nclip-miss target=2\n"));
	}

	@Test
	void askNeedsLoginAndUrgentCooldown() {
		assertFalse(LogReviewPolicy.shouldAsk(true, true, false, 199, true));
		assertTrue(LogReviewPolicy.shouldAsk(true, true, false, 200, true));
		assertFalse(LogReviewPolicy.shouldAsk(true, true, false, 2000, false));
		assertFalse(LogReviewPolicy.shouldAsk(false, true, false, 200, true));
		assertFalse(LogReviewPolicy.shouldAsk(true, false, false, 200, true));
		assertFalse(LogReviewPolicy.shouldAsk(true, true, true, 200, true));
	}

	@Test
	void scanEveryTwoSeconds() {
		assertFalse(LogReviewPolicy.scanThisTick(0));
		assertTrue(LogReviewPolicy.scanThisTick(40));
		assertFalse(LogReviewPolicy.scanThisTick(41));
	}
}
