package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.aihud.AiHudPolicy;

final class AiHudPolicyTest {
	@Test
	void staysUpWhileRunningThenHoldsAfterDone() {
		assertTrue(AiHudPolicy.visible(true, 1_000L, 0L));
		assertTrue(AiHudPolicy.visible(false, 1_000L, 1_500L));
		assertFalse(AiHudPolicy.visible(false, 2_000L, 1_500L));
		assertFalse(AiHudPolicy.visible(false, 1_000L, 0L));
	}

	@Test
	void elapsedFormatsMinutes() {
		assertEquals("已等 8 秒", AiHudPolicy.elapsed(0L, 8_000L));
		assertEquals("已等 1 分 5 秒", AiHudPolicy.elapsed(0L, 65_000L));
	}

	@Test
	void keepsLastSixDistinctSteps() {
		List<String> lines = List.of();
		for (int i = 1; i <= 8; i++) lines = AiHudPolicy.append(lines, "step-" + i);
		lines = AiHudPolicy.append(lines, "step-8");
		assertEquals(List.of("step-3", "step-4", "step-5", "step-6", "step-7", "step-8"), lines);
		assertEquals(6, AiHudPolicy.keepTail(lines).size());
	}
}
