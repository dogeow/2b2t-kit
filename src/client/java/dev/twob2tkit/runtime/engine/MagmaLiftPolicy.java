package dev.twob2tkit.runtime.engine;

/** Input arbitration for escaping a solid magma block, not lava fluid. */
public final class MagmaLiftPolicy {
    private MagmaLiftPolicy() {}

    public static boolean hasClearance(boolean chunksLoaded, boolean collisionFree, boolean fluidFree) {
        return chunksLoaded && collisionFree && fluidFree;
    }

    public record Input(boolean jump, boolean sneak) {}

    public static Input input(boolean flightStarted) {
        return flightStarted ? new Input(true, false) : new Input(false, true);
    }

    public static final int STALL_LIMIT_TICKS = 40;
    private static final double MIN_RISE = 0.02;

    /** Consecutive ticks the lift has been requested without the player gaining height. */
    public static int nextStall(int previous, double lastY, double y) {
        return y - lastY >= MIN_RISE ? 0 : previous + 1;
    }

    public static boolean stalled(int ticks) {
        return ticks >= STALL_LIMIT_TICKS;
    }

    public static final int LANDED_SUPPRESS_TICKS = 200;

    /** A flying player cannot crouch, and crouching is what stops magma burns: land before sneaking. */
    public static boolean mustLandToSneak(boolean flying, boolean onMagma) {
        return flying && onMagma;
    }
}
