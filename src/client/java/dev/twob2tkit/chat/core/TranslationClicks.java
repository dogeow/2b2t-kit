package dev.twob2tkit.chat.core;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.UUID;

/** Local opaque click tokens; no message text or server command is embedded. */
public final class TranslationClicks<T> {
    public static final String PREFIX = "kit-local-translation:";
    public record Claim<T>(String token, T value, long serial) { }
    private static final class Entry<T> {
        final T value; final Object connection; long serial; boolean busy;
        Entry(T value, Object connection) { this.value = value; this.connection = connection; }
    }
    private final int limit;
    private final LinkedHashMap<String, Entry<T>> entries = new LinkedHashMap<>();
    public TranslationClicks(int limit) { if (limit < 1) throw new IllegalArgumentException(); this.limit = limit; }
    public static boolean isToken(String value) { return value != null && value.startsWith(PREFIX); }
    public String register(T value, Object connection) {
        if (connection == null) throw new IllegalArgumentException("Current connection required");
        String token = PREFIX + UUID.randomUUID(); entries.put(token, new Entry<>(value, connection));
        while (entries.size() > limit) entries.remove(entries.keySet().iterator().next());
        return token;
    }
    public T get(String token, Object connection) {
        Entry<T> entry = entries.get(token);
        return entry != null && entry.connection == connection ? entry.value : null;
    }
    public Claim<T> claim(String token, Object connection) {
        Entry<T> entry = entries.get(token);
        if (entry == null || entry.connection != connection || entry.busy) return null;
        entry.busy = true; return new Claim<>(token, entry.value, ++entry.serial);
    }
    public boolean finish(Claim<T> claim) {
        Entry<T> entry = entries.get(claim.token());
        if (entry == null || !entry.busy || entry.serial != claim.serial() || entry.value != claim.value()) return false;
        entry.busy = false; return true;
    }
    public void cancelPending() { for (Entry<T> entry : entries.values()) { entry.serial++; entry.busy = false; } }
    public List<T> values() { return entries.values().stream().map(entry -> entry.value).toList(); }
    public void remove(String token) { entries.remove(token); }
    public void clear() { entries.clear(); }
}
