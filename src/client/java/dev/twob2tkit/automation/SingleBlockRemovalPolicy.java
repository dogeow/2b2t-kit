package dev.twob2tkit.automation;

/** Excavation removes the solid target; opted-in underwater gravel may refill with water. */
final class SingleBlockRemovalPolicy {
    private SingleBlockRemovalPolicy() {}
    static boolean removed(boolean air, boolean waterBlock, boolean underwaterGravel) {
        return air || underwaterGravel && waterBlock;
    }
}
