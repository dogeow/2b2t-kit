package dev.twob2tkit;

/** GUI units, not physical pixels. Every shared page uses the same viewport and HUD-safe footer. */
public record UiPageLayout(int left, int width, int top, int bottom, int footer) {
    public static UiPageLayout of(int screenWidth, int screenHeight) {
        int width = Math.max(280, Math.min(680, screenWidth - 24));
        int footer = Math.max(126, screenHeight - 80);
        return new UiPageLayout((screenWidth - width) / 2, width, 54, footer - 22, footer);
    }
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
