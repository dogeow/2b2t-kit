package dev.twob2tkit;

/** List-first geometry, independent of GUI scale; the footer retains the HUD's safe bottom margin. */
record SavedPlacesLayout(int left, int width, int toolbarY, int filterY, int listTop, int listHeight, int footerY) {
	static final int ROW_HEIGHT = 24;
	static SavedPlacesLayout of(int screenWidth, int screenHeight, boolean editorOpen) {
		// Keep control dimensions valid even during a transient minimized-window resize.
		int width = Math.max(280, Math.min(640, screenWidth - 24));
		int toolbar = editorOpen ? 94 : 36;
		int filter = toolbar + 24, top = filter + 26, footer = screenHeight - 80;
		return new SavedPlacesLayout((screenWidth - width) / 2, width, toolbar, filter, top, Math.max(0, footer - 6 - top), footer);
	}
	int coordinateWidth() { return (width - 24) / 5; }
	int nameWidth() { return width - 24 - 3 * coordinateWidth(); }
	int fieldX(int index) { return index == 0 ? left : left + nameWidth() + 8 + (index - 1) * (coordinateWidth() + 8); }
	int buttonWidth() { return (width - 18) / 4; }
	int buttonX(int index) { return left + index * (buttonWidth() + 6); }
	boolean listVisible() { return listHeight >= ROW_HEIGHT + 8; }
	int fullRows() { return Math.max(0, (listHeight - 8) / ROW_HEIGHT); }
	static int textWidth(int contentWidth) { return Math.max(1, contentWidth - 166); }
}
