package dev.twob2tkit.runtime.engine;

/** Preserve a still-valid clearance target rather than restarting the same block. */
public final class LootClearancePolicy {
    private LootClearancePolicy() {}
    public static boolean keepTarget(boolean sameTarget, boolean stillMineable) {
        return sameTarget && stillMineable;
    }
    public static boolean clearBeforePickup(boolean preferDrop, boolean inPickup,
                                            boolean embedded, boolean ceilingBlocked) {
        return !preferDrop && inPickup && !embedded && !ceilingBlocked;
    }
}
