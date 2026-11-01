package dev.twob2tkit.automation;

/** Explicit original-source construction exception; ordinary buckets retain strict defaults. */
final class ConstructionThermalBucketPolicy {
    private ConstructionThermalBucketPolicy() {}
    static boolean allow(boolean optedIn, boolean originalSource, boolean minorThermal,
                         double health, boolean recentMobAttack) {
        return optedIn && originalSource && minorThermal && Double.isFinite(health)
            && health >= 19 && !recentMobAttack;
    }
    static boolean recentMobAttack(boolean attackerPresent, int currentTick, int attackTick) {
        // Future timestamps and the full five-second combat window fail closed.
        return attackerPresent && ((long)currentTick - attackTick <= 100);
    }
}
