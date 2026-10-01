package dev.twob2tkit.runtime.engine;

/** Piglin interruption adds melee coordination without replacing existing ranged defense. */
final class BorerMiningCombatPolicy {
    static boolean meleeTarget(boolean piglin, boolean brute, boolean ranged, double distance, double verticalGap) {
        return piglin || brute || !ranged && distance <= 6 && Math.abs(verticalGap) <= 2;
    }
    private BorerMiningCombatPolicy() {}
}
