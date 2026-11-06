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
}
