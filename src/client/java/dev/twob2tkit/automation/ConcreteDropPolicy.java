package dev.twob2tkit.automation;

/** Never collect unrelated or pre-existing items to claim a batch succeeded. */
final class ConcreteDropPolicy {
    private ConcreteDropPolicy() {}

    static boolean eligible(boolean alive, boolean preexisting, boolean correctItem,
                            int stackCount, int missing, double cellDistanceSquared,
                            double playerDistance) {
        return alive && !preexisting && correctItem && stackCount > 0 && stackCount <= missing
            && cellDistanceSquared < 100 && playerDistance < 32;
    }

    /** A failed path search is retried only after new position evidence or a bounded wait. */
    static boolean shouldRetry(boolean sameUuid, double movementSquared, int ticksElapsed) {
        return !sameUuid || movementSquared >= .25 || ticksElapsed >= 20;
    }
}
