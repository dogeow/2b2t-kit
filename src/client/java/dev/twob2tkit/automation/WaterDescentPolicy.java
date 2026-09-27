package dev.twob2tkit.automation;

/** A short, straight-down pickup under water with a fixed air reserve. */
final class WaterDescentPolicy {
    private WaterDescentPolicy() {}

    static boolean allowed(boolean task, boolean guard, boolean underwater,
                           double health, int air, double horizontal, double drop) {
        return allowed(task,guard,underwater,health,air,horizontal,drop,260);
    }

    static boolean allowed(boolean task, boolean guard, boolean underwater,
                           double health, int air, double horizontal, double drop,int pickupFloor) {
        return task && guard && underwater && health >= 19 && air >= pickupFloor
            && horizontal <= 1.5 && drop >= .5 && drop <= 5;
    }

    static boolean continueDescent(boolean underwater, double health, int air) {
        return continueDescent(underwater,health,air,245);
    }

    static boolean continueDescent(boolean underwater, double health, int air,int returnFloor) {
        return underwater && health >= 19 && air >= returnFloor;
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
