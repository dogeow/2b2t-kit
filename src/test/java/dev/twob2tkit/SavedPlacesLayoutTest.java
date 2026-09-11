package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SavedPlacesLayoutTest {
	@Test void browseModeMoreThanDoublesTheFormerThreeRowViewport() {
		var layout = SavedPlacesLayout.of(600, 360, false);
		int oldHeight = 360 - 80 - 4 - 28 - 156;
		assertTrue(layout.listHeight() >= 2 * oldHeight);
		assertEquals(7, layout.fullRows()); // Dimension headings also occupy a row.
		assertEquals(576, layout.width());
	}
	@Test void editingUsesOnlyTheSpaceNeededForFieldsAndActions() {
		var browse = SavedPlacesLayout.of(600, 360, false);
		var edit = SavedPlacesLayout.of(600, 360, true);
		assertEquals(58, edit.listTop() - browse.listTop());
		assertEquals(58, browse.listHeight() - edit.listHeight());
		assertEquals(5, edit.fullRows());
		assertTrue(edit.toolbarY() >= 70 + 20 + 4);
		assertEquals(browse.footerY(), edit.footerY());
	}
	@Test void toolbarListAndFooterStaySeparateAtSupportedGuiSizes() {
		for (int width : new int[]{320, 427, 600, 1000}) for (int height : new int[]{240, 360, 720}) {
			for (boolean edit : new boolean[]{false, true}) {
				var layout = SavedPlacesLayout.of(width, height, edit);
				assertTrue(layout.left() >= 12);
				assertTrue(layout.left() + layout.width() <= width - 12);
				assertTrue(layout.filterY() >= layout.toolbarY() + 24);
				assertTrue(layout.listTop() >= layout.filterY() + 24);
				assertTrue(layout.listTop() + layout.listHeight() <= layout.footerY() - 6);
				assertTrue(layout.footerY() + 20 <= height - 56);
			}
		}
	}
	@Test void fieldsAndFourButtonColumnsFitWithoutOverlap() {
		for (int width : new int[]{320, 427, 600, 1000}) {
			var layout = SavedPlacesLayout.of(width, 360, true);
			assertEquals(layout.left(), layout.fieldX(0));
			assertEquals(layout.fieldX(0) + layout.nameWidth() + 8, layout.fieldX(1));
			for (int i = 1; i < 3; i++) assertEquals(layout.fieldX(i) + layout.coordinateWidth() + 8, layout.fieldX(i + 1));
			assertEquals(layout.left() + layout.width(), layout.fieldX(3) + layout.coordinateWidth());
			for (int i = 0; i < 3; i++) assertEquals(layout.buttonX(i) + layout.buttonWidth() + 6, layout.buttonX(i + 1));
			assertTrue(layout.buttonX(3) + layout.buttonWidth() <= layout.left() + layout.width());
		}
	}
	@Test void smallWindowHidesUnusableListUntilEditorIsCollapsed() {
		var edit = SavedPlacesLayout.of(320, 240, true);
		assertFalse(edit.listVisible()); assertEquals(0, edit.fullRows());
		var browse = SavedPlacesLayout.of(320, 240, false);
		assertTrue(browse.listVisible()); assertEquals(2, browse.fullRows());
	}
	@Test void minimizedWindowNeverProducesNegativeWidgetDimensions() {
		for (boolean edit : new boolean[]{false, true}) {
			var layout = SavedPlacesLayout.of(1, 1, edit);
			assertTrue(layout.nameWidth() > 0); assertTrue(layout.coordinateWidth() > 0);
			assertTrue(layout.buttonWidth() > 0); assertTrue(layout.width() - 100 > 0);
			assertFalse(layout.listVisible()); assertEquals(0, layout.listHeight());
		}
	}
	@Test void longTextStopsBeforeTheFirstActionButton() {
		for (int contentWidth : new int[]{264, 560, 624}) {
			int guideLeft = contentWidth - 158;
			assertEquals(guideLeft - 8, SavedPlacesLayout.textWidth(contentWidth));
		}
		assertEquals(1, SavedPlacesLayout.textWidth(0));
	}
	@Test void increasingWindowUsesExtraRoomButKeepsComfortableMaximumWidth() {
		assertTrue(SavedPlacesLayout.of(600, 480, false).fullRows() > SavedPlacesLayout.of(600, 360, false).fullRows());
		assertEquals(640, SavedPlacesLayout.of(1000, 720, false).width());
		assertTrue(SavedPlacesLayout.of(600, 360, false).width() > SavedPlacesLayout.of(320, 360, false).width());
	}
}
