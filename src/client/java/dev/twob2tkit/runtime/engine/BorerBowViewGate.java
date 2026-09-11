package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;

/** A scheduled look alone is not proof that the player has seen the aiming direction. */
final class BorerBowViewGate {
    private RotationAim.Look rendered;
    private int renderedAt = Integer.MIN_VALUE;
    void reset() { rendered = null; renderedAt = Integer.MIN_VALUE; }
    void rendered(RotationAim.Look look, int tick) { rendered = look; renderedAt = tick; }
    boolean ready(RotationAim.Look wanted, RotationAim.Look cameraNow, int tick) {
        return rendered != null && tick >= renderedAt && (long)tick - renderedAt <= 2
            && aligned(wanted, rendered) && aligned(wanted, cameraNow);
    }
    static boolean aligned(RotationAim.Look a, RotationAim.Look b) {
        if (a == null || b == null || !Float.isFinite(a.yaw()) || !Float.isFinite(a.pitch())
            || !Float.isFinite(b.yaw()) || !Float.isFinite(b.pitch())) return false;
        double yaw = ((a.yaw() - b.yaw() + 180) % 360 + 360) % 360 - 180;
        // A 0.25 block/tick strafe at 3 blocks turns ~5 degrees between rendered frames.
        // Reject a genuinely different view without deadlocking close moving targets.
        return Math.abs(yaw) <= 6 && Math.abs(a.pitch() - b.pitch()) <= 6;
    }
}
