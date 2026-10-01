package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class SavedPlaceHomePolicyTest {
	@Test void selectionIsUniqueAndCaseInsensitive() {
		assertEquals(1, SavedPlaceHomePolicy.selectedIndex(List.of("主基地", "下界门", "村庄"), "下界门"));
		assertEquals(0, SavedPlaceHomePolicy.selectedIndex(List.of("Home", "home"), "HOME"));
	}

	@Test void unknownOrEmptyNameSelectsNothing() {
		assertEquals(-1, SavedPlaceHomePolicy.selectedIndex(List.of("主基地"), "不存在"));
		assertEquals(-1, SavedPlaceHomePolicy.selectedIndex(List.of("主基地"), ""));
		assertEquals(-1, SavedPlaceHomePolicy.selectedIndex(List.of("主基地"), null));
	}
}
