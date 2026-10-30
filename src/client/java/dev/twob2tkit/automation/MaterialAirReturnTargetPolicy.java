package dev.twob2tkit.automation;

/** A nearby upward return to observed air, independent of the world's sea level. */
final class MaterialAirReturnTargetPolicy {
    private MaterialAirReturnTargetPolicy() {}
    static boolean allowed(double feet, double target, int minY, int maxY) {
        return Double.isFinite(feet) && Double.isFinite(target)
            && minY < maxY && feet >= minY && target + 1.8 < maxY
            && target >= feet + 1 && target - feet <= 64;
    }
}
