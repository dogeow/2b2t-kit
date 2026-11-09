package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import java.util.LinkedHashMap;

/** One reappearance per confirmed clearance, independent of target selection churn. */
final class BorerReappearance {
    private record Evidence(long clearedAt, long lastReappearance, int count, boolean awaiting) {}

    private final LinkedHashMap<BlockPos, Evidence> evidence = new LinkedHashMap<>();

    void clear() {
        evidence.clear();
    }

    void confirmedClear(BlockPos pos, long now) {
        var previous = evidence.remove(pos);
        boolean recent = previous != null
            && BorerMiningPolicy.reappearedAfterClear(now, previous.lastReappearance(), false);
        evidence.put(pos.immutable(), new Evidence(now, recent ? previous.lastReappearance() : now,
            recent ? previous.count() : 0, true));
        if (evidence.size() > 64) evidence.pollFirstEntry();
    }

    int observe(BlockPos pos, long now, boolean solid, boolean falling) {
        var previous = evidence.get(pos);
        if (!solid || previous == null || !previous.awaiting()
            || !BorerMiningPolicy.reappearedAfterClear(now, previous.clearedAt(), falling)) return 0;
        int count = previous.count() + 1;
        evidence.put(pos, new Evidence(previous.clearedAt(), now, count, false));
        return count;
    }
}
