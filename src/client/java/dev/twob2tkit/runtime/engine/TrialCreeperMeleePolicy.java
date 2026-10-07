package dev.twob2tkit.runtime.engine;

import java.util.UUID;

/** A bounded hit-and-retreat cycle, enabled only by the installed host's exact trial ownership check. */
final class TrialCreeperMeleePolicy {
    static final double RESET_DISTANCE = 7.5;
    static final int NO_DAMAGE_TICKS = 160;
    static final int MAX_DURATION_TICKS = 800;
    enum Decision { APPROACH, ATTACK, WAIT, RETREAT, UNAVAILABLE }
    record Step(Decision decision, String reason) {}

    static boolean eligible(boolean authorized, boolean current, boolean alive, boolean visible,
                            boolean powered, boolean ignited, boolean bowAvailable, double distance) {
        return authorized && current && alive && visible && !powered && !ignited && !bowAvailable
            && Double.isFinite(distance) && distance >= 0 && distance <= 12;
    }
    /** Full-strength damage is discounted for the .95 cooldown threshold; enchantment bonuses are unnecessary. */
    static int swordReserve(double health, double fullDamage) {
        if (!Double.isFinite(health) || health <= 0 || !Double.isFinite(fullDamage) || fullDamage <= 0)
            return Integer.MAX_VALUE;
        double swings = Math.ceil(health / (fullDamage * .9));
        return swings > Integer.MAX_VALUE - 2 ? Integer.MAX_VALUE : Math.max(5, (int)swings + 2);
    }

    private UUID target;
    private long started, progressAt, lastTick, pausedAt = Long.MIN_VALUE;
    private double originX, originZ, lowestHealth;
    private boolean retreating, exhausted;
    private String exhaustedReason = "";

    Step step(UUID id, long tick, double x, double z, double distance, double health,
              boolean swelling, boolean inRange, boolean cooledDown,
              boolean approachClear, boolean retreatClear) {
        if (id == null || tick < 0 || !Double.isFinite(x) || !Double.isFinite(z)
            || !Double.isFinite(distance) || distance < 0 || !Double.isFinite(health) || health <= 0)
            return new Step(Decision.UNAVAILABLE, "invalid_observation");
        if (!id.equals(target)) {
            target = id; started = progressAt = lastTick = tick;
            originX = x; originZ = z; lowestHealth = health;
            retreating = exhausted = false; pausedAt = Long.MIN_VALUE; exhaustedReason = "";
        }
        if (pausedAt != Long.MIN_VALUE) {
            long duration = Math.max(0, tick - pausedAt);
            started += duration; progressAt += duration;
            pausedAt = Long.MIN_VALUE;
        }
        if (tick < lastTick) return unavailable("clock_changed");
        lastTick = tick;
        if (exhausted) return new Step(Decision.UNAVAILABLE, exhaustedReason);
        if (health < lowestHealth) { lowestHealth = health; progressAt = tick; }
        if (tick - started > MAX_DURATION_TICKS) return unavailable("time_limit");
        if (tick - progressAt >= NO_DAMAGE_TICKS) return unavailable("no_confirmed_damage");
        if (Math.hypot(x - originX, z - originZ) > 12 || distance > 12) return unavailable("travel_limit");
        if (swelling) retreating = true;
        if (retreating) {
            if (!swelling && distance >= RESET_DISTANCE) retreating = false;
            else return retreatClear ? new Step(Decision.RETREAT, "reset_fuse") : unavailable("retreat_blocked");
        }
        // A safe escape must exist before approaching or swinging, including while cooldown is pending.
        if (!retreatClear) return unavailable("no_safe_escape");
        if (inRange) return new Step(cooledDown ? Decision.ATTACK : Decision.WAIT,
            cooledDown ? "within_reach" : "attack_cooldown");
        return approachClear ? new Step(Decision.APPROACH, "clear_short_step") : unavailable("approach_blocked");
    }
    void attacked() { retreating = true; }
    void pause(long tick) { if (target != null && pausedAt == Long.MIN_VALUE) pausedAt = tick; }
    void reset() { target = null; exhausted = retreating = false; pausedAt = Long.MIN_VALUE; }
    private Step unavailable(String reason) {
        exhausted = true; exhaustedReason = reason;
        return new Step(Decision.UNAVAILABLE, reason);
    }
}
