package dev.twob2tkit.piglin;

import java.util.Locale;

/** Status only; never grants attacks or movement. */
final class BrawlerStatusPolicy {
    private BrawlerStatusPolicy() {}
    static String piglinStatus(double distance, double meleeReach, boolean ownMelee) {
        if (!Double.isFinite(distance) || distance < 0 || distance > 64)
            return "64格内未发现已加载的猪人";
        if (!ownMelee)
            return String.format(Locale.ROOT, "附近有猪人（%.1f格）；近战交给Meteor", distance);
        if (distance > meleeReach)
            return String.format(Locale.ROOT, "附近有猪人（%.1f格）；近战需接近至%.1f格", distance, meleeReach);
        return String.format(Locale.ROOT, "附近有猪人（%.1f格）；等待攻击条件", distance);
    }
}
