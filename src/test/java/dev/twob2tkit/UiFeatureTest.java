package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class UiFeatureTest {
    @Test void oneCatalogContainsEveryPlannedFeatureAndSevenCategories() {
        assertEquals(7, UiFeature.Category.values().length); assertEquals(33, UiFeature.values().length);
        for (String id : List.of("AREA", "ORE", "FORWARD", "DOWN", "ROUTE", "BORER_SAFETY", "CRUISE", "CRUISE_OPTIONS", "PLACES", "SCENERY", "STRUCTURES", "STRUCTURE_MARKS", "DEATH", "CHOPPER", "PLANTER", "FEEDER", "FISHER", "CONCRETE", "SKILLS", "BUILDER", "VILLAGER", "BRAWLER", "STORAGE", "CHECKLIST", "RECIPES", "GUARD", "SURROUND", "SURVIVAL", "HEALING", "TRUSTED", "SETTINGS", "KEYBINDS", "DIAGNOSTICS"))
            assertNotNull(UiFeature.find(id), id);
    }
    @Test void searchMatchesOldNamesAndCommonTermsWithoutLaunchingActions() {
        assertTrue(UiFeature.CHOPPER.matches("挖树")); assertTrue(UiFeature.AREA.matches("AB"));
        assertTrue(UiFeature.AREA.matches("盾构机")); assertTrue(UiFeature.CHECKLIST.matches("行动指南"));
        assertTrue(UiFeature.SCENERY.matches("bobby")); assertTrue(UiFeature.BORER_SAFETY.matches("箱子"));
        assertTrue(UiFeature.ORE.matches("钻石")); assertTrue(UiFeature.PLACES.matches("地点 收藏"));
        assertFalse(UiFeature.PLACES.matches("自动 钓鱼"));
    }
    @Test void staleConfigIdsCannotBreakNavigation() {
        assertNull(UiFeature.find(null)); assertNull(UiFeature.find("REMOVED"));
        assertEquals(UiFeature.Category.HOME, UiFeature.Category.parse(null));
        assertEquals(UiFeature.Category.HOME, UiFeature.Category.parse("old"));
        assertEquals(UiFeature.Category.STORAGE, UiFeature.Category.parse("STORAGE"));
    }
    @Test void everyCategoryHasFeaturesAndEveryFeatureHasReadableLabels() {
        for (var category : UiFeature.Category.values()) if (category != UiFeature.Category.HOME)
            assertTrue(Arrays.stream(UiFeature.values()).anyMatch(f -> f.category == category));
        for (var f : UiFeature.values()) { assertFalse(f.title.isBlank()); assertFalse(f.description.isBlank()); }
    }
}
