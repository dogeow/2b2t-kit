package dev.twob2tkit.runtime.engine;

/** Only observed aggression starts combat with otherwise neutral Nether mobs. */
final class BorerPiglinPolicy {
    static boolean ordinaryThreat(boolean visible, boolean recentAttacker, boolean targetingOther,
                                  boolean targetingPlayer, boolean goldArmor, boolean baby,
                                  boolean admiring, boolean aggressive, boolean facing,
                                  boolean approaching, double distance, double verticalGap) {
        if (recentAttacker) return true;
        if (!visible || targetingOther || baby || admiring) return false;
        if (targetingPlayer) return distance <= 10;
        // Gold armor calms an idle piglin. A synchronized attack pose remains evidence
        // of aggression after a provocation even if the player is wearing gold.
        if (aggressive && facing && distance <= 10 && Math.abs(verticalGap) <= 3) return true;
        return !goldArmor && facing && approaching && distance <= 8 && Math.abs(verticalGap) <= 3;
    }
    static boolean zombifiedThreat(boolean visible, boolean recentAttacker, boolean targetingOther,
                                   boolean targetingPlayer, boolean aggressive, boolean facing,
                                   boolean approaching, double distance, double verticalGap) {
        if (recentAttacker) return true;
        if (!visible || targetingOther) return false;
        return targetingPlayer && distance <= 10
            || aggressive && facing && (approaching || distance <= 3)
                && distance <= 10 && Math.abs(verticalGap) <= 3;
    }
    static boolean goldArmorItem(String id) {
        return id.equals("golden_helmet") || id.equals("golden_chestplate")
            || id.equals("golden_leggings") || id.equals("golden_boots");
    }
    private BorerPiglinPolicy() {}
}
