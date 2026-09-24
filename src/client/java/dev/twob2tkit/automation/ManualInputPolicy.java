package dev.twob2tkit.automation;

/** Debounce genuine foreground keyboard/mouse activity before handing off control. */
public final class ManualInputPolicy {
    private static final long RECENT_MS = 600;

    private ManualInputPolicy() {}

    public static boolean mouseMoved(double dx, double dy) {
        return Double.isFinite(dx) && Double.isFinite(dy)
            && Math.hypot(dx, dy) >= .75;
    }

    public static boolean recent(long now, long last, boolean focused, boolean screenOpen) {
        return focused && !screenOpen && last > 0 && now >= last && now-last <= RECENT_MS;
    }
}
