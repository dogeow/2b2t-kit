package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.logreview.LogReviewAsk;

final class LogReviewAskTest {
	@Test
	void parsesLessonJson() {
		LogReviewAsk.Advice advice = LogReviewAsk.parse(
			"{\"need_fix\":true,\"lesson\":\"剪刀快坏会被取消破坏\",\"cause\":\"shears-worn\"}");
		assertTrue(advice.needFix);
		assertEquals("剪刀快坏会被取消破坏", advice.lesson);
		assertEquals("shears-worn", advice.cause);
	}

	@Test
	void promptMentionsChopperLog() {
		assertTrue(LogReviewAsk.promptText("chopper", "stall skip=1").contains("chopper"));
		assertTrue(LogReviewAsk.promptText("chopper", "stall skip=1").contains("stall skip=1"));
		assertTrue(LogReviewAsk.promptText("surround", "no-block").contains("surround"));
		assertTrue(LogReviewAsk.promptText("builder", "place-fail").contains("place-fail"));
	}

	@Test
	void parsesGrokCliResultWrapper() {
		LogReviewAsk.Advice advice = LogReviewAsk.parse(
			"{\"type\":\"result\",\"result\":\"{\\\"need_fix\\\":true,\\\"lesson\\\":\\\"收成不要按攻击键\\\",\\\"cause\\\":\\\"villager\\\"}\"}");
		assertTrue(advice.needFix);
		assertEquals("收成不要按攻击键", advice.lesson);
		assertEquals("villager", advice.cause);
	}

	@Test
	void parsesLastJsonLineOfNdjson() {
		LogReviewAsk.Advice advice = LogReviewAsk.parse(
			"{\"type\":\"assistant\"}\n{\"need_fix\":false,\"lesson\":\"先走近再收\",\"cause\":\"clip-miss\"}\n");
		assertFalse(advice.needFix);
		assertEquals("先走近再收", advice.lesson);
	}
}
