package dev.twob2tkit.automation;

import java.util.Set;

/** One bounded food use may run during an eating-only guard hold. */
final class AutomationFoodPolicy {
    private static final Set<String> RECOVERY_FOOD = Set.of(
        "minecraft:cooked_beef", "minecraft:cooked_porkchop", "minecraft:cooked_chicken",
        "minecraft:cooked_mutton", "minecraft:cooked_cod", "minecraft:cooked_salmon",
        "minecraft:bread", "minecraft:baked_potato");

    private AutomationFoodPolicy() {}

    static boolean allow(boolean localSurvival, boolean ownedMaterials, boolean hostileNearby,
                         boolean menuOpen, boolean manualMovement, float health, int food) {
        return (localSurvival || ownedMaterials) && !hostileNearby && !menuOpen && !manualMovement
            && health >= 14 && food < 20;
    }

    static boolean maySelectRecoveryFood(String item, boolean guardedOwner, boolean hostileNearby,
                                         boolean menuOpen, boolean manualMovement, boolean safeFooting,
                                         float health, int food) {
        return safeFooting && RECOVERY_FOOD.contains(item)
            && allow(false, guardedOwner, hostileNearby, menuOpen, manualMovement, health, food);
    }
}
