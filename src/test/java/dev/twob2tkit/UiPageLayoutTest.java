package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class UiPageLayoutTest {
    @Test void fieldsAndFooterFitAtEachSupportedGuiSize() {
        for (int w : new int[]{320, 427, 600, 960, 1280}) for (int h : new int[]{240, 360, 540, 720}) {
            var p = UiPageLayout.of(w, h);
            assertTrue(p.left() >= 12); assertTrue(p.left() + p.width() <= w - 12);
            assertTrue(p.labelWidth() >= 80); assertTrue(p.fieldWidth() >= 86);
            assertEquals(p.left() + p.width(), p.fieldX() + p.fieldWidth());
            assertTrue(p.left() + p.labelWidth() + 8 < p.fieldX());
            assertTrue(p.bottom() < p.footer()); assertTrue(p.footer() + 20 <= h - 56);
        }
    }
    @Test void sevenCategoryButtonsAndThreeActionsNeverOverlap() {
        for (int w : new int[]{320, 427, 600, 960}) {
            var p = UiPageLayout.of(w, 360); int nav = (p.width() - 18) / 7;
            assertTrue(nav >= 38); assertTrue(7 * nav + 18 <= p.width());
            for (int count : new int[]{2, 3, 4}) for (int i = 1; i < count; i++) {
                assertTrue(p.buttonX(i - 1, count) + p.buttonWidth(count) < p.buttonX(i, count));
                assertTrue(p.buttonX(i, count) + p.buttonWidth(count) <= p.left() + p.width());
            }
        }
    }
    @Test void collectionsReserveSpaceForSearchAndFiltersButUseRemainingHeight() {
        var p = UiPageLayout.of(600, 360);
        assertEquals(64, p.collectionTop(false)); assertEquals(90, p.collectionTop(true));
        assertTrue((p.collectionHeight(true) - 8) / 24 >= 7);
        assertEquals(p.footer() - 6, p.collectionTop(true) + p.collectionHeight(true));
        assertEquals(26, p.collectionHeight(false) - p.collectionHeight(true));
    }
    @Test void smallScreenStillHasUsableListAndHiddenRowsCannotBeConsideredVisible() {
        var p = UiPageLayout.of(320, 240);
        assertTrue(p.collectionHeight(true) >= 48);
        assertFalse(p.fullyVisible(p.top() - 1, 20)); assertFalse(p.fullyVisible(p.bottom() - 19, 20));
        assertTrue(p.fullyVisible(p.top(), 20)); assertTrue(p.fullyVisible(p.bottom() - 20, 20));
    }
    @Test void scrollingClampsWhenFilteringOrRemovingItems() {
        var p = UiPageLayout.of(600, 360);
        assertEquals(0, p.clampScroll(99, 0)); assertEquals(0, p.clampScroll(-10, 500));
        assertEquals(500 - p.height(), p.clampScroll(999, 500));
    }
    @Test void minimizedResizeKeepsAllControlDimensionsPositive() {
        var p = UiPageLayout.of(1, 1);
        assertTrue(p.width() > 0); assertTrue(p.fieldWidth() > 0); assertTrue(p.height() > 0); assertTrue(p.buttonWidth(4) > 0);
    }
    @Test void footerButtonsHaveACapAndTheirGroupIsCentered() {
        for (int width : new int[]{320, 427, 600, 960, 1280}) for (int count = 1; count <= 4; count++) {
            var p = UiPageLayout.of(width, 360); int w = p.footerButtonWidth(count);
            assertTrue(w > 0 && w <= 150);
            int start = p.footerButtonX(0, count), end = p.footerButtonX(count - 1, count) + w;
            assertTrue(start >= p.left()); assertTrue(end <= p.left() + p.width());
            assertTrue(Math.abs((start - p.left()) - (p.left() + p.width() - end)) <= 1);
            for (int i = 1; i < count; i++) assertEquals(p.footerButtonX(i - 1, count) + w + 6, p.footerButtonX(i, count));
        }
    }
    @Test void compactFootersDoNotShrinkFiltersOrDataListArea() {
        var p = UiPageLayout.of(960, 540);
        assertEquals(680, p.width()); assertEquals(337, p.buttonWidth(2));
        assertEquals(150, p.footerButtonWidth(2)); assertEquals(150, p.footerButtonWidth(1));
        assertEquals(p.footer() - 6, p.collectionTop(true) + p.collectionHeight(true));
    }
}
