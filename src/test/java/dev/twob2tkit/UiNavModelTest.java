package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class UiNavModelTest {
    private static List<UiFeature> features(List<UiNavModel.Row> rows) {
        return rows.stream().filter(r -> r.kind() == UiNavModel.Kind.FEATURE).map(UiNavModel.Row::feature).toList();
    }
    @Test void overviewThenOneGroupPerCategoryWithEveryNavigationEntry() {
        var rows = UiNavModel.rows("", null, null);
        assertEquals(UiNavModel.Kind.OVERVIEW, rows.getFirst().kind());
        assertEquals(6, rows.stream().filter(r -> r.kind() == UiNavModel.Kind.HEADER).count());
        assertEquals(28, features(rows).size());
        assertTrue(features(rows).stream().allMatch(UiFeature::listed));
    }
    @Test void favoritesComeFirstAsTheirNavigationEntryOnce() {
        var rows = UiNavModel.rows("", List.of("DEATH", "PLACES", "ORE"), null);
        assertEquals("★ 收藏", rows.get(1).label().substring(2));
        assertEquals(List.of(UiFeature.PLACES, UiFeature.ORE), features(rows).subList(0, 2));
    }
    @Test void collapsedGroupsHideOnlyTheirRows() {
        Set<String> collapsed = new HashSet<>();
        UiNavModel.toggle(collapsed, "PRODUCTION");
        var rows = UiNavModel.rows("", null, collapsed);
        assertFalse(features(rows).contains(UiFeature.CHOPPER));
        assertTrue(features(rows).contains(UiFeature.ORE));
        assertTrue(rows.stream().anyMatch(r -> r.kind() == UiNavModel.Kind.HEADER && r.label().startsWith("▸ 生产")));
        UiNavModel.toggle(collapsed, "PRODUCTION");
        assertTrue(features(UiNavModel.rows("", null, collapsed)).contains(UiFeature.CHOPPER));
    }
    @Test void searchListsSubPagesTooAndSaysWhenNothingMatches() {
        assertTrue(features(UiNavModel.rows("死亡", null, null)).contains(UiFeature.DEATH));
        var none = UiNavModel.rows("不存在的功能xyz", null, null);
        assertEquals(1, none.size()); assertEquals("没有匹配功能", none.getFirst().label());
    }
    @Test void scrollAndRowLookupStayInRange() {
        var rows = UiNavModel.rows("", null, null);
        int content = UiNavModel.contentHeight(rows);
        assertEquals(0, UiNavModel.clampScroll(-5, content, 100));
        assertEquals(content - 100, UiNavModel.clampScroll(99999, content, 100));
        assertEquals(0, UiNavModel.clampScroll(50, 40, 100));
        assertEquals(-1, UiNavModel.rowAt(rows, -1)); assertEquals(-1, UiNavModel.rowAt(rows, content));
        assertEquals(1, UiNavModel.rowAt(rows, UiNavModel.ROW_HEIGHT));
    }
}
