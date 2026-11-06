package dev.twob2tkit.runtime.engine;

/** Bounded recovery when a miner cannot immediately step onto the next column. */
public final class BorerNoSupportPolicy {
    private BorerNoSupportPolicy() {}
    public static boolean walkSafeDrop(boolean grounded, boolean touchingFluid, boolean standingOnMagma,
                                       boolean immediateFluid, int safeDrop) {
        return grounded && !touchingFluid && !standingOnMagma && !immediateFluid && safeDrop > 0;
    }
    public static boolean replanOre(boolean oreMode, boolean collectingLoot, int blockedTicks) {
        return oreMode && !collectingLoot && blockedTicks >= 80;
    }
    public static boolean stopUnroutable(boolean oreMode, boolean hasOreGoal, boolean collectingLoot, int blockedTicks) {
        return (!oreMode || !hasOreGoal) && !collectingLoot && blockedTicks >= 200;
    }
}
