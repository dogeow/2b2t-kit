package dev.twob2tkit;

/** Feature shortcuts are compact tiles, not full-width data-list rows. All dimensions are GUI units. */
record UiFeatureGridLayout(int left, int columns, int cardWidth, int count) {
    static final int GAP = 12;
    static final int ROW_HEIGHT = 40;
    static final int FAVORITE_WIDTH = 22;
    static final int ACTION_GAP = 4;
    static final int MAX_CARD_WIDTH = 260;
    static final int MIN_TWO_COLUMN_WIDTH = 220 * 2 + GAP;

    static UiFeatureGridLayout of(UiPageLayout page, int count) {
        count = Math.max(0, count);
        int columns = count >= 2 && page.width() >= MIN_TWO_COLUMN_WIDTH ? 2 : 1;
        int cardWidth = Math.min(MAX_CARD_WIDTH, (page.width() - (columns - 1) * GAP) / columns);
        int total = columns * cardWidth + (columns - 1) * GAP;
        return new UiFeatureGridLayout(page.left() + (page.width() - total) / 2, columns, cardWidth, count);
    }
    int x(int index) { return left + (index % columns) * (cardWidth + GAP); }
    int y(int index, int top) { return top + (index / columns) * ROW_HEIGHT; }
    int openWidth() { return cardWidth - FAVORITE_WIDTH - ACTION_GAP; }
    int favoriteX(int index) { return x(index) + cardWidth - FAVORITE_WIDTH; }
    int contentHeight() { return ((count + columns - 1) / columns) * ROW_HEIGHT; }
}
