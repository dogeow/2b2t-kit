package dev.twob2tkit.storage;

import dev.twob2tkit.KitConfig;
import java.util.List;

/** Bounded cache retention favors supplies and named containers over empty transit hoppers. */
public final class StorageCache {
    public static final int MAX_RECORDS = 512, MAX_EMPTY_HOPPERS = 64;
    private StorageCache() {}

    public static boolean hasItems(KitConfig.StorageSnapshot record) {
        return record.items != null && record.items.stream().anyMatch(i -> i != null && i.count > 0);
    }
    private static boolean emptyHopper(KitConfig.StorageSnapshot record) {
        return "minecraft:hopper".equals(record.blockId) && !hasItems(record)
            && (record.note == null || record.note.isBlank()) && !hasHistoricalItems(record);
    }
    private static boolean hasHistoricalItems(KitConfig.StorageSnapshot record) {
        return record.history != null && record.history.stream().anyMatch(h -> h != null && h.items != null
            && h.items.stream().anyMatch(i -> i != null && i.count > 0));
    }
    private static int priority(KitConfig.StorageSnapshot record) {
        if (record.note != null && !record.note.isBlank()) return 3;
        if (hasItems(record) || hasHistoricalItems(record)) return 2;
        return emptyHopper(record) ? 0 : 1;
    }
    public static void trim(List<KitConfig.StorageSnapshot> records) {
        while (records.stream().filter(StorageCache::emptyHopper).count() > MAX_EMPTY_HOPPERS)
            records.remove(oldest(records, true));
        while (records.size() > MAX_RECORDS) records.remove(oldest(records, false));
    }
    private static int oldest(List<KitConfig.StorageSnapshot> records, boolean hopperOnly) {
        int victim = -1;
        for (int i = 0; i < records.size(); i++) {
            var candidate = records.get(i);
            if (hopperOnly && !emptyHopper(candidate)) continue;
            if (victim < 0 || priority(candidate) < priority(records.get(victim))
                || priority(candidate) == priority(records.get(victim))
                    && candidate.lastSeenEpochMillis <= records.get(victim).lastSeenEpochMillis) victim = i;
        }
        return victim;
    }
}
