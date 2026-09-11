package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UiFeatureGridLayoutTest {
    @Test void productionShortcutsUseTwoCompactColumnsOnTheReportedWideWindow() {
        var page = UiPageLayout.of(600, 320);
        var grid = UiFeatureGridLayout.of(page, 7);
        assertEquals(2, grid.columns()); assertEquals(260, grid.cardWidth());
        assertEquals(234, grid.openWidth());
        assertTrue(grid.openWidth() < (page.width() - 34) / 2);
        assertEquals(grid.y(0, 64), grid.y(1, 64));
        assertEquals(grid.y(0, 64) + 40, grid.y(2, 64));
        assertEquals(160, grid.contentHeight());
        assertTrue(grid.y(6, 64) + 32 <= page.footer() - 22, "All seven production shortcuts and descriptions fit");
    }
    @Test void narrowWindowUsesOneCenteredColumnWithoutStretchingButtons() {
        var page = UiPageLayout.of(320, 240); var grid = UiFeatureGridLayout.of(page, 7);
        assertEquals(1, grid.columns()); assertEquals(260, grid.cardWidth());
        assertEquals(page.left() + (page.width() - grid.cardWidth()) / 2, grid.left());
        assertEquals(grid.x(0), grid.x(6)); assertEquals(280, grid.contentHeight());
    }
    @Test void columnThresholdNeverCreatesAnUndersizedSecondColumn() {
        var narrow = UiFeatureGridLayout.of(UiPageLayout.of(475, 360), 7);
        var wide = UiFeatureGridLayout.of(UiPageLayout.of(476, 360), 7);
        assertEquals(1, narrow.columns()); assertEquals(2, wide.columns()); assertEquals(220, wide.cardWidth());
    }
    @Test void searchWithOneOrZeroResultsDoesNotLeaveAnEmptySecondColumn() {
        var page = UiPageLayout.of(960, 540);
        var one = UiFeatureGridLayout.of(page, 1);
        var empty = UiFeatureGridLayout.of(page, 0);
        assertEquals(1, one.columns()); assertEquals(40, one.contentHeight());
        assertEquals(page.left() + (page.width() - one.cardWidth()) / 2, one.left());
        assertEquals(0, empty.contentHeight());
    }
    @Test void cardsFavoriteButtonsAndDescriptionsStayWithinTheirOwnColumns() {
        for (int width : new int[]{320, 475, 476, 600, 960, 1280}) for (int count : new int[]{0, 1, 2, 7, 31}) {
            var page = UiPageLayout.of(width, 360); var grid = UiFeatureGridLayout.of(page, count);
            assertTrue(grid.cardWidth() <= UiFeatureGridLayout.MAX_CARD_WIDTH);
            for (int i = 0; i < count; i++) {
                assertTrue(grid.x(i) >= page.left()); assertTrue(grid.x(i) + grid.cardWidth() <= page.left() + page.width());
                assertEquals(grid.x(i) + grid.openWidth() + 4, grid.favoriteX(i));
                assertEquals(grid.x(i) + grid.cardWidth(), grid.favoriteX(i) + 22);
                if (i % grid.columns() != 0) assertTrue(grid.x(i - 1) + grid.cardWidth() < grid.x(i));
                assertTrue(grid.y(i, 0) + 32 <= grid.contentHeight());
            }
        }
    }
    @Test void resizeAndSearchShrinkContentSoOldScrollCanBeClamped() {
        var page = UiPageLayout.of(600, 360);
        var grid = UiFeatureGridLayout.of(page, 31);
        assertEquals(640, grid.contentHeight());
        assertEquals(0, page.clampScroll(999, UiFeatureGridLayout.of(page, 1).contentHeight()));
        assertTrue(grid.contentHeight() < UiFeatureGridLayout.of(UiPageLayout.of(320, 360), 31).contentHeight());
    }
}
