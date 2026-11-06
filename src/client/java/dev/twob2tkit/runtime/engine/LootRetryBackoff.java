package dev.twob2tkit.runtime.engine;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** Short-lived retry pacing; never claims an item was collected. */
public final class LootRetryBackoff {
    private static final int BASE_TICKS = 600; // 30 seconds at 20 ticks/sec
    private static final int MAX_ATTEMPTS = 3;
    private static final int MAX_TRACKED = 256;
    private final Map<UUID, Integer> failures = new LinkedHashMap<>();

    public int nextDelay(UUID item) {
        if (item == null) throw new IllegalArgumentException("Item identity is required");
        if (!failures.containsKey(item) && failures.size() >= MAX_TRACKED)
            failures.remove(failures.keySet().iterator().next());
        int attempts = Math.min(MAX_ATTEMPTS, failures.getOrDefault(item, 0) + 1);
        failures.put(item, attempts);
        return BASE_TICKS * attempts;
    }

    public void clear() { failures.clear(); }
}
