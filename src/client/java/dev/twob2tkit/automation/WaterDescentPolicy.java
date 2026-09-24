package dev.twob2tkit.automation;

/** A short, straight-down pickup under water with a fixed air reserve. */
final class WaterDescentPolicy {
    private WaterDescentPolicy() {}

    static boolean allowed(boolean task, boolean guard, boolean underwater,
                           double health, int air, double horizontal, double drop) {
        return task && guard && underwater && health >= 19 && air >= 260
            && horizontal <= 1.5 && drop >= .5 && drop <= 5;
    }

    static boolean continueDescent(boolean underwater, double health, int air) {
        return underwater && health >= 19 && air >= 245;
    }

    static boolean atTarget(double currentY, double targetY) {
        return Math.abs(currentY-targetY) <= .35;
    }

    static boolean sink(double currentY, double targetY) {
        return targetY-currentY < -.15;
    }

    static boolean align(double horizontal) {
        return horizontal > .2;
    }
}
