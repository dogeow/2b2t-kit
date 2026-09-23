package dev.twob2tkit.automation;

/** One bounded food use may run during an eating-only guard hold. */
final class AutomationFoodPolicy {
    private AutomationFoodPolicy() {}

    static boolean allow(boolean localSurvival, boolean ownedMaterials, boolean hostileNearby,
                         boolean menuOpen, boolean manualMovement, float health, int food) {
        return (localSurvival || ownedMaterials) && !hostileNearby && !menuOpen && !manualMovement
            && health >= 14 && food < 20;
    }
}
