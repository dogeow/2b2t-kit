package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static dev.twob2tkit.runtime.engine.BorerMealPolicy.Action.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerMealPolicyTest {
	@Test void yieldsBeforeNativeEatingHasStarted() {
		var pause = new BorerMealPolicy();
		assertEquals(PAUSE, pause.tick(true, false, false, 16, 10));
		assertTrue(pause.paused());
	}
	@Test void alreadyEatingOrManualFoodAlsoPausesMining() {
		assertEquals(PAUSE, new BorerMealPolicy().tick(false, true, false, 19, 20));
		assertEquals(PAUSE, new BorerMealPolicy().tick(false, false, true, 19, 20));
	}
	@Test void doesNotStealControlBetweenTwoFoodsOrWhenThresholdNoLongerRequestsButStillUsing() {
		var pause = new BorerMealPolicy();
		assertEquals(PAUSE, pause.tick(true, true, true, 12, 20));
		assertEquals(PAUSE, pause.tick(false, false, false, 16, 20));
		assertEquals(PAUSE, pause.tick(true, true, true, 16, 20));
		assertEquals(PAUSE, pause.tick(false, false, true, 20, 20));
		assertEquals(PAUSE, pause.tick(false, false, false, 20, 20));
		assertEquals(RESUME, pause.tick(false, false, false, 20, 20));
		assertFalse(pause.paused());
		assertEquals(WORK, pause.tick(false, false, false, 20, 20));
	}
	@Test void blockedAutoEatWithoutFoodProgressHasBoundedWaitEvenWithAnimation() {
		for (boolean animation : new boolean[] {false, true}) {
			var pause = new BorerMealPolicy();
			for (int i = 0; i < 199; i++) assertEquals(PAUSE, pause.tick(true, animation, animation, 12, 10));
			assertEquals(BLOCKED, pause.tick(true, animation, animation, 12, 10));
		}
	}
	@Test void ActualNutritionProgressRefreshesWaitBudget() {
		var pause = new BorerMealPolicy();
		for (int i = 0; i < 190; i++) pause.tick(true, true, true, 10, 10);
		assertEquals(PAUSE, pause.tick(true, true, true, 14, 10));
		for (int i = 0; i < 190; i++) assertEquals(PAUSE, pause.tick(true, true, true, 14, 10));
		assertEquals(PAUSE, pause.tick(true, true, true, 14, 11));
	}
	@Test void DisabledAutoEatResumesAndNewSessionDoesNotInheritPause() {
		var pause = new BorerMealPolicy(); pause.tick(true, false, false, 16, 10);
		assertEquals(PAUSE, pause.tick(false, false, false, 16, 10));
		assertEquals(RESUME, pause.tick(false, false, false, 16, 10));
		pause.tick(true, false, false, 16, 10); pause.reset();
		assertEquals(WORK, pause.tick(false, false, false, 16, 10));
	}
}
