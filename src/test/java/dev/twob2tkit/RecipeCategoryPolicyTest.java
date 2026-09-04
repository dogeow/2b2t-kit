package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.recipe.RecipeCategoryPolicy;

final class RecipeCategoryPolicyTest {
	private static final List<String> TABS = List.of("building", "blocks", "redstone", "equipment", "food", "misc");

	@Test
	void jsonBuildingStaysBuildingEvenWhenBlock() {
		assertEquals("building", RecipeCategoryPolicy.displayCategory("building", true, false));
		assertFalse(RecipeCategoryPolicy.matches("blocks", "building", true, false));
	}

	@Test
	void miscBlockGoesToBlocksMiscFoodGoesToFood() {
		assertEquals("blocks", RecipeCategoryPolicy.displayCategory("misc", true, false));
		assertEquals("food", RecipeCategoryPolicy.displayCategory("misc", false, true));
		assertEquals("misc", RecipeCategoryPolicy.displayCategory("misc", false, false));
	}

	@Test
	void partitionCountsSumToAll() {
		record Sample(String jsonCategory, boolean block, boolean food) {
		}
		List<Sample> samples = List.of(
			new Sample("building", true, false),
			new Sample("redstone", true, false),
			new Sample("equipment", false, false),
			new Sample("misc", true, false),
			new Sample("misc", false, true),
			new Sample("misc", false, false),
			new Sample("food", false, true)
		);
		long sum = TABS.stream().mapToLong(tab -> samples.stream()
			.filter(s -> RecipeCategoryPolicy.matches(tab, s.jsonCategory(), s.block(), s.food()))
			.count()).sum();
		assertEquals(samples.size(), sum);
		assertTrue(RecipeCategoryPolicy.matches("all", "misc", true, false));
	}
}
