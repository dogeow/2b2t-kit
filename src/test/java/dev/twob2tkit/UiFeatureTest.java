package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class UiFeatureTest {
    @Test void oneCatalogContainsEveryPlannedFeatureAndSevenCategories() {
        assertEquals(7, UiFeature.Category.values().length); assertEquals(35, UiFeature.values().length);
        for (String id : List.of("AREA", "ORE", "GRAVEL", "FORWARD", "DOWN", "ROUTE", "BORER_SAFETY", "CRUISE", "CRUISE_OPTIONS", "PLACES", "SCENERY", "STRUCTURES", "STRUCTURE_MARKS", "DEATH", "CHOPPER", "PLANTER", "FEEDER", "FISHER", "CONCRETE", "MATERIALS", "SKILLS", "BUILDER", "VILLAGER", "BRAWLER", "STORAGE", "CHECKLIST", "RECIPES", "GUARD", "SURROUND", "SURVIVAL", "HEALING", "TRUSTED", "SETTINGS", "KEYBINDS", "DIAGNOSTICS"))
            assertNotNull(UiFeature.find(id), id);
    }
    @Test void searchMatchesOldNamesAndCommonTermsWithoutLaunchingActions() {
        assertTrue(UiFeature.CHOPPER.matches("挖树")); assertTrue(UiFeature.AREA.matches("AB"));
        assertTrue(UiFeature.AREA.matches("盾构机")); assertTrue(UiFeature.CHECKLIST.matches("行动指南"));
        assertTrue(UiFeature.SCENERY.matches("bobby")); assertTrue(UiFeature.BORER_SAFETY.matches("箱子"));
        assertTrue(UiFeature.ORE.matches("钻石")); assertTrue(UiFeature.PLACES.matches("地点 收藏"));
        assertTrue(UiFeature.GRAVEL.matches("水下 沙砾"));
        assertFalse(UiFeature.GRAVEL.matches("盾构机"));
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
    @Test void homeContainsOnlyExplicitFavoritesInSavedOrder() {
        assertEquals(List.of(UiFeature.CONCRETE, UiFeature.AREA),
            UiFeature.visible(UiFeature.Category.HOME, "", List.of("CONCRETE", "REMOVED", "AREA", "CONCRETE")));
        assertEquals(List.of(), UiFeature.visible(UiFeature.Category.HOME, "", null));
        assertEquals(List.of(), UiFeature.visible(UiFeature.Category.HOME, "  ", List.of()));
    }
    @Test void homeSearchCanFindUnfavoritedFunctionsWithoutMutatingFavorites() {
        var favorites = new ArrayList<>(List.of("CONCRETE"));
        assertEquals(List.of(UiFeature.FISHER), UiFeature.visible(UiFeature.Category.HOME, "钓鱼", favorites));
        assertEquals(List.of("CONCRETE"), favorites);
        assertEquals(List.of(UiFeature.CONCRETE), UiFeature.visible(UiFeature.Category.HOME, "", favorites));
    }
    @Test void switchingCategoryCannotRetainAHiddenSearchFilter() {
        var features = UiFeature.visible(UiFeature.Category.MINING, "钓鱼", List.of("CONCRETE"));
        assertTrue(features.containsAll(List.of(UiFeature.AREA, UiFeature.ORE, UiFeature.GRAVEL)));
        assertTrue(features.stream().allMatch(f -> f.category == UiFeature.Category.MINING));
        assertEquals(UiFeature.visible(UiFeature.Category.MINING, "", null), features);
    }
}
