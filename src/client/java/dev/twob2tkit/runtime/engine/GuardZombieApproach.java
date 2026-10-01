package dev.twob2tkit.runtime.engine;

import java.util.UUID;

/** Small, cancelable hover approach toward one already engaged zombie. */
final class GuardZombieApproach {
    enum Decision { MOVE, ATTACK, UNAVAILABLE }
    record Step(Decision decision, String reason) {}

    /** Meteor Velocity applies 15x speed while sprinting (10x normally).
     * Keep either actual step inside the collision sweep planned at 10x. */
    static double sprintSafeSpeed(double plannedSpeed) {
        return plannedSpeed * .65;
    }

    private UUID target;
    private int started, lastProgress, retryAfter;
    private double originX, originZ, bestDistance;

    Step step(UUID id, int tick, double x, double z, double targetX, double targetZ,
              boolean attackReach, boolean safeHover, boolean clearStep) {
        if (!safeHover) return unavailable(tick, "unsafe_height");
        double distance = Math.hypot(targetX - x, targetZ - z);
        if (target == null || !target.equals(id)) {
            if (tick < retryAfter) return new Step(Decision.UNAVAILABLE, "retry_cooldown");
            target = id;
            started = lastProgress = tick;
            originX = x; originZ = z; bestDistance = distance;
        }
        if (distance > 9.0) return unavailable(tick, "target_out_of_range");
        if (Math.hypot(x - originX, z - originZ) > 8.5) return unavailable(tick, "travel_limit");
        if (attackReach) return new Step(Decision.ATTACK, "within_reach");
        if (tick - started > 160) return unavailable(tick, "time_limit");
        if (distance < bestDistance - .05) {
            bestDistance = distance;
            lastProgress = tick;
        }
        if (tick - lastProgress > 20) return unavailable(tick, "stalled");
        if (!clearStep) return unavailable(tick, "path_blocked");
        return new Step(Decision.MOVE, "clear_short_step");
    }

    void reset() {
        target = null;
        retryAfter = 0;
    }

    private Step unavailable(int tick, String reason) {
        target = null;
        retryAfter = tick + 80;
        return new Step(Decision.UNAVAILABLE, reason);
    }
}
