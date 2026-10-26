package dev.twob2tkit.runtime.engine;

/** Only actual or retained combat threats preempt a collision-checked side peek. */
final class GuardRepositionThreatPolicy {
    static boolean blocks(boolean alive, boolean creeperOrRanged,
                          boolean observedEngagement, boolean retainedEngagement) {
        return alive && creeperOrRanged && (observedEngagement || retainedEngagement);
    }
    private GuardRepositionThreatPolicy() {}
}
