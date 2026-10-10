package dev.twob2tkit.automation;

import java.util.Set;

/** Use the existing precise dry navigator only for above-water gravel transit. */
final class GravelNavigationPolicy {
    private static final Set<String> DRY_STAGES = Set.of(
        "SETTLE_HIGH", "SETTLE_SURFACE", "PARK", "REFILL");

    private GravelNavigationPolicy() {}

    static boolean dryTransit(String stage, boolean underwater,
                              double currentY, double targetY, double returnY) {
        return stage != null && DRY_STAGES.contains(stage) && !underwater
            && Double.isFinite(currentY) && Double.isFinite(targetY) && Double.isFinite(returnY)
            && currentY >= returnY - .5 && targetY >= returnY;
    }
}
