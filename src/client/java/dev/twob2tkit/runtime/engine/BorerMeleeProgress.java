package dev.twob2tkit.runtime.engine;

import java.util.UUID;

/** Module activation is not evidence of damage; retry with normal melee after a short grace period. */
final class BorerMeleeProgress {
    static final int NATIVE_GRACE_TICKS = 20;
    private UUID target;
    private float lowestHealth;
    private int progressAt;
    boolean stalled(UUID id, int tick, float health) {
        if (!id.equals(target) || tick < progressAt || health < lowestHealth) {
            target = id;
            lowestHealth = health;
            progressAt = tick;
        }
        return tick - progressAt >= NATIVE_GRACE_TICKS;
    }
    void clear() { target = null; }
}
