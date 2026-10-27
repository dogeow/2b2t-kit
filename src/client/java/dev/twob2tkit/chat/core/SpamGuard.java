package dev.twob2tkit.chat.core;

import java.text.Normalizer;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Session-local duplicate filtering. Callers own sender authentication and any server command. */
public final class SpamGuard {
    private static final int MAX_SENDERS = 1024;
    private static final int MAX_BLOCKED = 1024;
    private final int threshold;
    private final long windowMillis;
    private final Map<String, Repeats> senders = new LinkedHashMap<>(32, 0.75f, true);
    private final Set<String> blocked = new LinkedHashSet<>();

    public SpamGuard(int threshold, long windowMillis) {
        if (threshold < 2) {
            throw new IllegalArgumentException("Spam threshold must be at least 2");
        }
        if (windowMillis <= 0) {
            throw new IllegalArgumentException("Spam window must be positive");
        }
        this.threshold = threshold;
        this.windowMillis = windowMillis;
    }

    /**
     * A repeated message is hidden from its second occurrence. Reaching the threshold
     * inside a fixed window blocks that identity until clear() or unblock().
     */
    public synchronized Decision inspect(String playerKey, String text, long now) {
        Objects.requireNonNull(playerKey, "playerKey");
        Objects.requireNonNull(text, "text");
        if (playerKey.isBlank()) {
            throw new IllegalArgumentException("Sender identity cannot be blank");
        }
        if (blocked.contains(playerKey)) {
            return new Decision(true, false);
        }
        String normalized = normalize(text);
        Repeats previous = senders.get(playerKey);
        if (previous == null || !previous.text().equals(normalized) || now < previous.startedAt()
                || now - previous.startedAt() >= windowMillis) {
            senders.put(playerKey, new Repeats(normalized, now, 1));
            trimSenders();
            return new Decision(false, false);
        }
        int count = Math.min(threshold, previous.count() + 1);
        senders.put(playerKey, new Repeats(normalized, previous.startedAt(), count));
        if (count >= threshold && blocked.size() < MAX_BLOCKED) {
            blocked.add(playerKey);
            senders.remove(playerKey);
            return new Decision(true, true);
        }
        return new Decision(true, false);
    }

    public synchronized boolean blocked(String playerKey) {
        return blocked.contains(playerKey);
    }

    /** Restores or manually adds a session block; false means already blocked or capacity reached. */
    public synchronized boolean block(String playerKey) {
        Objects.requireNonNull(playerKey, "playerKey");
        if (playerKey.isBlank()) {
            throw new IllegalArgumentException("Sender identity cannot be blank");
        }
        if (blocked.size() >= MAX_BLOCKED || !blocked.add(playerKey)) {
            return false;
        }
        senders.remove(playerKey);
        return true;
    }

    public synchronized boolean unblock(String playerKey) {
        senders.remove(playerKey);
        return blocked.remove(playerKey);
    }

    public synchronized Set<String> blockedPlayers() {
        return Collections.unmodifiableSet(new LinkedHashSet<>(blocked));
    }

    public synchronized void clear() {
        blocked.clear();
        senders.clear();
    }

    /** Normalizes presentation-only differences without altering the chat displayed to the user. */
    public static String normalize(String text) {
        String normalized = Normalizer.normalize(ChatText.stripFormatting(text), Normalizer.Form.NFKC)
                .toLowerCase(Locale.ROOT);
        StringBuilder result = new StringBuilder(normalized.length());
        boolean pendingSpace = false;
        for (int offset = 0; offset < normalized.length();) {
            int codePoint = normalized.codePointAt(offset);
            offset += Character.charCount(codePoint);
            if (Character.getType(codePoint) == Character.FORMAT) {
                continue;
            }
            if (Character.isWhitespace(codePoint) || Character.isSpaceChar(codePoint)) {
                pendingSpace = !result.isEmpty();
                continue;
            }
            if (pendingSpace) {
                result.append(' ');
                pendingSpace = false;
            }
            result.appendCodePoint(codePoint);
        }
        return result.toString();
    }

    private void trimSenders() {
        if (senders.size() > MAX_SENDERS) {
            senders.remove(senders.keySet().iterator().next());
        }
    }

    public record Decision(boolean suppress, boolean newlyBlocked) { }

    private record Repeats(String text, long startedAt, int count) { }
}
