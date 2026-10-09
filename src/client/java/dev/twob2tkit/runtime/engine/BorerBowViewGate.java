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
        double pitchA = Math.toRadians(a.pitch()), pitchB = Math.toRadians(b.pitch());
        double yaw = Math.toRadians((double)a.yaw() - b.yaw());
        // Compare the actual view directions. Near straight down, a large yaw
        // change can still represent less than one degree of aiming movement.
        double dot = Math.sin(pitchA) * Math.sin(pitchB)
            + Math.cos(pitchA) * Math.cos(pitchB) * Math.cos(yaw);
        return dot >= Math.cos(Math.toRadians(6));
    }
}
