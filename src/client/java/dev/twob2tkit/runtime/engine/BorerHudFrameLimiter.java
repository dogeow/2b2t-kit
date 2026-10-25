package dev.twob2tkit.runtime.engine;

/** Sample both HUD lines together; do not delay a new safety warning. */
final class BorerHudFrameLimiter {
    record Frame(String action, int color, String detail) {}
    private Frame frame;
    private long shownAt;
    Frame update(String action, int color, String detail, long now) {
        String text = action == null ? "" : action;
        String extra = detail == null ? "" : detail;
        boolean urgent = (color == 0xFF5555 || color == 0x55FF55)
            && (frame == null || frame.color() != color || !frame.action().equals(text));
        if (frame == null || now < shownAt || now - shownAt >= 250 || urgent) {
            frame = new Frame(text, color, extra);
            shownAt = now;
        }
        return frame;
    }
    void clear() { frame = null; }
}
