package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class UiFeatureTest {
    private static final List<String> OLD_IDS = List.of("AREA", "ORE", "GRAVEL", "FORWARD", "DOWN", "ROUTE", "BORER_SAFETY", "CRUISE", "CRUISE_OPTIONS",
        "PLACES", "SCENERY", "STRUCTURES", "STRUCTURE_MARKS", "DEATH", "CHOPPER", "PLANTER", "FEEDER", "FISHER", "CONCRETE", "CARETAKER", "MATERIALS",
        "SKILLS", "BUILDER", "VILLAGER", "BRAWLER", "STORAGE", "CHECKLIST", "RECIPES", "GUARD", "SURROUND", "SURVIVAL", "HEALING", "TRUSTED",
        "SETTINGS", "CHAT_TRANSLATION", "KEYBINDS", "DIAGNOSTICS");

    @Test void settingsCategoryKeepsFourFocusedEntries() {
        assertEquals(List.of(UiFeature.SETTINGS, UiFeature.KEYBINDS, UiFeature.CHAT_TRANSLATION, UiFeature.DIAGNOSTICS),
            UiFeature.visible(UiFeature.Category.SETTINGS, "", List.of()));
        assertTrue(UiFeature.DIAGNOSTICS.matches("热更新"));
    }
    @Test void navigationHasTwentyEightEntriesAndEveryOldIdStillResolves() {
        assertEquals(7, UiFeature.Category.values().length);
        assertEquals(28, Arrays.stream(UiFeature.values()).filter(UiFeature::listed).count());
        for (String id : OLD_IDS) { var f = UiFeature.find(id); assertNotNull(f, id); assertTrue(f.nav().listed(), id); }
        assertNull(UiFeature.find("SINGLEPLAYER_TRIAL")); assertNull(UiFeature.find("LOCAL_DECISION"));
    }
    @Test void mergedEntriesPointAtTheirNewHome() {
        assertEquals(UiFeature.ORE, UiFeature.GRAVEL.nav());
        assertEquals(UiFeature.TUNNEL, UiFeature.FORWARD.nav()); assertEquals(UiFeature.TUNNEL, UiFeature.DOWN.nav());
        assertEquals(UiFeature.MINING_COMMON, UiFeature.ROUTE.nav()); assertEquals(UiFeature.MINING_COMMON, UiFeature.BORER_SAFETY.nav());
        assertEquals(UiFeature.CRUISE, UiFeature.CRUISE_OPTIONS.nav()); assertEquals(UiFeature.PLACES, UiFeature.DEATH.nav());
        assertEquals(UiFeature.STRUCTURES, UiFeature.STRUCTURE_MARKS.nav()); assertEquals(UiFeature.MATERIALS, UiFeature.SKILLS.nav());
        assertEquals(UiFeature.SURVIVAL, UiFeature.HEALING.nav()); assertEquals(UiFeature.GUARD, UiFeature.TRUSTED.nav());
        for (var f : UiFeature.values()) assertEquals(f.category, f.nav().category, f.name());
    }
    @Test void searchMatchesOldNamesAndCommonTermsWithoutLaunchingActions() {
        assertTrue(UiFeature.CHOPPER.matches("挖树")); assertTrue(UiFeature.AREA.matches("AB"));
        assertTrue(UiFeature.AREA.matches("盾构机")); assertTrue(UiFeature.CHECKLIST.matches("行动指南"));
        assertTrue(UiFeature.SCENERY.matches("bobby")); assertTrue(UiFeature.BORER_SAFETY.matches("箱子"));
        assertTrue(UiFeature.ORE.matches("钻石")); assertTrue(UiFeature.PLACES.matches("地点 收藏"));
        assertTrue(UiFeature.GRAVEL.matches("水下 沙砾"));
        assertTrue(UiFeature.CHAT_TRANSLATION.matches("双语")); assertTrue(UiFeature.CHAT_TRANSLATION.matches("mct"));
        assertFalse(UiFeature.GRAVEL.matches("盾构机")); assertFalse(UiFeature.PLACES.matches("自动 钓鱼"));
        assertTrue(UiFeature.visible(UiFeature.Category.HOME, "死亡点", null).contains(UiFeature.DEATH));
        assertTrue(UiFeature.visible(UiFeature.Category.HOME, "巡航选项", null).contains(UiFeature.CRUISE_OPTIONS));
        assertTrue(UiFeature.visible(UiFeature.Category.HOME, "向下挖", null).contains(UiFeature.TUNNEL));
    }
    @Test void staleConfigIdsCannotBreakNavigation() {
        assertNull(UiFeature.find(null)); assertNull(UiFeature.find("REMOVED"));
        assertEquals(UiFeature.Category.HOME, UiFeature.Category.parse(null));
        assertEquals(UiFeature.Category.STORAGE, UiFeature.Category.parse("STORAGE"));
    }
    @Test void everyCategoryHasEntriesAndEveryFeatureHasReadableLabels() {
        for (var category : UiFeature.Category.values()) if (category != UiFeature.Category.HOME) assertFalse(UiFeature.listed(category).isEmpty());
        for (var f : UiFeature.values()) { assertFalse(f.title.isBlank()); assertFalse(f.description.isBlank()); }
    }
    @Test void favoritesMapOldIdsToTheirEntryWithoutDuplicatesOrRewritingTheSavedList() {
        var saved = new ArrayList<>(List.of("CONCRETE", "REMOVED", "DEATH", "PLACES", "CRUISE_OPTIONS", "CONCRETE"));
        assertEquals(List.of(UiFeature.CONCRETE, UiFeature.PLACES, UiFeature.CRUISE), UiFeature.visible(UiFeature.Category.HOME, "", saved));
        assertEquals(List.of("CONCRETE", "REMOVED", "DEATH", "PLACES", "CRUISE_OPTIONS", "CONCRETE"), saved);
        assertEquals(List.of(), UiFeature.visible(UiFeature.Category.HOME, "", null));
        assertEquals(List.of(), UiFeature.visible(UiFeature.Category.HOME, "  ", List.of()));
    }
    @Test void categoryListsIgnoreTheSearchAndShowOnlyNavigationEntries() {
        var features = UiFeature.visible(UiFeature.Category.MINING, "钓鱼", List.of("CONCRETE"));
        assertEquals(List.of(UiFeature.AREA, UiFeature.ORE, UiFeature.TUNNEL, UiFeature.MINING_COMMON), features);
    }
}
