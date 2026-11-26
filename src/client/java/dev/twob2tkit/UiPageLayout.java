package dev.twob2tkit;

/**
 * GUI units, not physical pixels. Every shared page uses the same viewport and HUD-safe footer.
 * On screens wide enough the left column holds the toolbox navigation and pages use the area to its right.
 */
public record UiPageLayout(int left, int width, int top, int bottom, int footer) {
    /** Narrower screens hide the navigation column; pages keep the full width and a menu button. */
    public static final int SIDEBAR_MIN_SCREEN = 430;
    public static final int SIDEBAR_X = 6;
    private static final int SIDEBAR_GAP = 8;

    /** Width of the navigation column, or 0 when the screen is too narrow for it. */
    public static int sidebarWidth(int screenWidth) {
        return screenWidth < SIDEBAR_MIN_SCREEN ? 0 : Math.max(110, Math.min(150, screenWidth * 22 / 100));
    }

    /** Content area to the right of the navigation column. */
    public static UiPageLayout of(int screenWidth, int screenHeight) {
        int sidebar = sidebarWidth(screenWidth);
        return sidebar == 0 ? full(screenWidth, screenHeight) : pane(screenWidth, screenHeight, SIDEBAR_X + sidebar + SIDEBAR_GAP);
    }

    /** Whole-screen page for dialogs that never show navigation. */
    public static UiPageLayout full(int screenWidth, int screenHeight) {
        int width = Math.max(280, Math.min(680, screenWidth - 24));
        int footer = Math.max(126, screenHeight - 80);
        return new UiPageLayout((screenWidth - width) / 2, width, 54, footer - 22, footer);
    }

    private static UiPageLayout pane(int screenWidth, int screenHeight, int start) {
        int room = screenWidth - start - 12, width = Math.max(1, Math.min(680, room));
        int footer = Math.max(126, screenHeight - 80);
        return new UiPageLayout(start + (room - width) / 2, width, 54, footer - 22, footer);
    }

    /** The overview needs slightly more content space while leaving the normal HUD below its footer. */
    public static UiPageLayout workspace(int screenWidth, int screenHeight) {
        var base = of(screenWidth, screenHeight); int footer = Math.max(126, screenHeight - 72);
        return new UiPageLayout(base.left(), base.width(), 54, footer - 22, footer);
    }
    public int center() { return left + width / 2; }
    public int height() { return Math.max(20, bottom - top); }
    public int fieldWidth() { return Math.max(86, Math.min(220, width * 2 / 5)); }
    public int fieldX() { return left + width - fieldWidth(); }
    public int labelWidth() { return width - fieldWidth() - 12; }
    public int collectionTop(boolean filters) { return filters ? 90 : 64; }
    public int collectionHeight(boolean filters) { return Math.max(24, footer - 6 - collectionTop(filters)); }
    public int buttonWidth(int count) { return (width - (count - 1) * 6) / count; }
    public int buttonX(int index, int count) { return left + index * (buttonWidth(count) + 6); }
    /** Footer actions have a comfortable maximum width; filters and data lists still use the full page. */
    public int footerButtonWidth(int count) { return Math.min(150, buttonWidth(count)); }
    public int footerButtonX(int index, int count) {
        int buttonWidth = footerButtonWidth(count), total = count * buttonWidth + (count - 1) * 6;
        return left + (width - total) / 2 + index * (buttonWidth + 6);
    }
    public boolean fullyVisible(int y, int h) { return y >= top && y + h <= bottom; }
    public int clampScroll(int scroll, int contentHeight) { return Math.max(0, Math.min(scroll, Math.max(0, contentHeight - height()))); }
}
