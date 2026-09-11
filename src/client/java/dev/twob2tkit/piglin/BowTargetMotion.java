package dev.twob2tkit.piglin;

import net.minecraft.world.phys.Vec3;

/** Position samples are authoritative for remote mobs; their client deltaMovement may remain zero. */
final class BowTargetMotion {
    private Vec3 position, velocity = Vec3.ZERO;
    private long tick = Long.MIN_VALUE;
    private int still;
    Vec3 observe(long now, Vec3 current, Vec3 hint, boolean onGround) {
        if (!finite(current)) { reset(); return Vec3.ZERO; }
        if (position == null || now < tick || now - tick > 6) {
            position = current; tick = now; still = 0;
            velocity = clamp(hint == null ? Vec3.ZERO : hint, onGround); return velocity;
        }
        if (now == tick) return velocity;
        Vec3 measured = current.subtract(position).scale(1.0 / (now - tick));
        position = current; tick = now;
        if (!finite(measured) || measured.lengthSqr() > 4) { velocity = Vec3.ZERO; still = 0; return velocity; }
        measured = clamp(measured, onGround);
        if (measured.lengthSqr() < .0001) {
            velocity = ++still >= 2 ? Vec3.ZERO : velocity.scale(.25); return velocity;
        }
        still = 0;
        double dot = measured.x * velocity.x + measured.z * velocity.z;
        double denominator = Math.hypot(measured.x, measured.z) * Math.hypot(velocity.x, velocity.z);
        // A strafe reversal or sharp turn must not keep aiming at the previous direction.
        double blend = denominator < .00001 || dot / denominator < .5 ? 1.0 : .7;
        velocity = velocity.scale(1 - blend).add(measured.scale(blend));
        return velocity;
    }
    void reset() { position = null; velocity = Vec3.ZERO; tick = Long.MIN_VALUE; still = 0; }
    private static Vec3 clamp(Vec3 v, boolean ground) {
        if (!finite(v)) return Vec3.ZERO;
        double horizontal = Math.hypot(v.x, v.z), scale = horizontal > .8 ? .8 / horizontal : 1;
        return new Vec3(v.x * scale, ground ? 0 : Math.max(-1, Math.min(1, v.y)), v.z * scale);
    }
    private static boolean finite(Vec3 v) { return v != null && Double.isFinite(v.x) && Double.isFinite(v.y) && Double.isFinite(v.z); }
}
