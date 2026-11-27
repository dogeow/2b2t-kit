package dev.twob2tkit.logreview;

/**
 * De-duplicates a diagnostic line by a stable key (target and outcome, not the player's
 * sub-block position), letting the same key through again only after {@code repeatMillis}.
 */
public final class RepeatLogGate {
    private final long repeatMillis;
    private String lastKey = "";
    private long lastAt;

    public RepeatLogGate(long repeatMillis) { this.repeatMillis = repeatMillis; }

    public boolean allow(String key, long now) {
        if (key.equals(lastKey) && now - lastAt < repeatMillis) return false;
        lastKey = key; lastAt = now; return true;
    }

    public void reset() { lastKey = ""; lastAt = 0; }
}
