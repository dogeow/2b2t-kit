package dev.twob2tkit.piglin;

import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import java.util.Optional;

/** Deterministic discrete arrow physics + moving-box interception. No Minecraft client singleton or side effects. */
final class BowTrajectory {
    static final double DRAG = .99, GRAVITY = .05;
    static final int MAX_TICKS = 100;
    interface World {
        /** First blocking terrain or other entity on this arrow segment. */
        Optional<Vec3> obstruction(Vec3 from, Vec3 to);
        default boolean targetSpace(AABB box) { return true; }
    }
    record Solution(Vec3 direction, double flightTicks, Vec3 predictedCenter) {}
    static Solution solve(Vec3 start, Vec3 inherited, AABB target, Vec3 motion, double latency, double speed, World world) {
        if (!finite(start) || !finite(inherited) || !finite(motion) || !Double.isFinite(speed) || speed <= .01) return null;
        latency = Double.isFinite(latency) ? Math.max(0, Math.min(4, latency)) : 0;
        AABB[] positions = forecast(target, motion, latency, world);
        for (double height : new double[]{.5, .7, .3}) {
            double previousT = .05, previous = required(start, inherited, positions, previousT, height).length() - speed;
            for (double time = .5; time <= MAX_TICKS; time += .5) {
                double error = required(start, inherited, positions, time, height).length() - speed;
                if (previous > 0 && error <= 0) {
                    double lo = previousT, hi = time;
                    for (int i = 0; i < 20; i++) {
                        double mid = (lo + hi) * .5;
                        if (required(start, inherited, positions, mid, height).length() > speed) lo = mid; else hi = mid;
                    }
                    double flight = (lo + hi) * .5;
                    Vec3 direction = required(start, inherited, positions, flight, height).normalize();
                    double hit = hitTime(start, direction.scale(speed).add(inherited), positions, world);
                    if (hit >= 0) return new Solution(direction, hit, boxAt(positions, hit).getCenter());
                    break; // Try another part of the same body, not an unvalidated high arc.
                }
                previousT = time; previous = error;
            }
        }
        return null;
    }
    /** Forecast can slide along a wall, but cannot extrapolate a walking mob through solid blocks. */
    static AABB[] forecast(AABB box, Vec3 velocity, double latency, World world) {
        int extra = (int)Math.ceil(latency);
        AABB[] raw = new AABB[MAX_TICKS + extra + 2]; raw[0] = box;
        double dx = velocity.x, dy = velocity.y, dz = velocity.z;
        for (int i = 1; i < raw.length; i++) {
            AABB next = raw[i - 1];
            if (dx != 0) { if (world.targetSpace(next.move(dx, 0, 0))) next = next.move(dx, 0, 0); else dx = 0; }
            if (dz != 0) { if (world.targetSpace(next.move(0, 0, dz))) next = next.move(0, 0, dz); else dz = 0; }
            if (dy != 0) { if (world.targetSpace(next.move(0, dy, 0))) next = next.move(0, dy, 0); else dy = 0; }
            raw[i] = next;
        }
        AABB[] result = new AABB[MAX_TICKS + 1];
        for (int i = 0; i < result.length; i++) result[i] = boxAt(raw, i + latency);
        return result;
    }
    private static Vec3 required(Vec3 start, Vec3 inherited, AABB[] positions, double time, double height) {
        AABB box = boxAt(positions, time);
        Vec3 point = new Vec3((box.minX + box.maxX) * .5, box.minY + (box.maxY - box.minY) * height, (box.minZ + box.maxZ) * .5);
        int whole = (int)Math.floor(time); double part = time - whole, drag = Math.pow(DRAG, whole);
        double distanceFactor = (1 - drag) / (1 - DRAG) + part * drag;
        double fall = GRAVITY * ((whole - (1 - drag) / (1 - DRAG)) / (1 - DRAG) + part * (1 - drag) / (1 - DRAG));
        return point.subtract(start).add(0, fall, 0).scale(1 / distanceFactor).subtract(inherited);
    }
    static AABB boxAt(AABB[] boxes, double time) {
        int index = Math.max(0, Math.min(boxes.length - 1, (int)Math.floor(time)));
        if (index == boxes.length - 1) return boxes[index];
        Vec3 delta = boxes[index + 1].getCenter().subtract(boxes[index].getCenter()).scale(Math.max(0, Math.min(1, time - index)));
        return boxes[index].move(delta);
    }
    /** Compare the arrow segment against the target's relative motion during the same tick. */
    static double hitTime(Vec3 start, Vec3 initialVelocity, AABB[] targets, World world) {
        Vec3 position = start, velocity = initialVelocity;
        for (int tick = 0; tick < MAX_TICKS; tick++) {
            Vec3 next = position.add(velocity);
            // Require the real body: vanilla's age-dependent projectile margin is only extra forgiveness.
            AABB box = targets[tick];
            Vec3 relativeEnd = next.subtract(targets[tick + 1].getCenter().subtract(targets[tick].getCenter()));
            Optional<Vec3> relativeHit = box.contains(position) ? Optional.of(position) : box.clip(position, relativeEnd);
            double fraction = relativeHit.isEmpty() ? Double.POSITIVE_INFINITY
                : position.distanceTo(relativeHit.get()) / Math.max(1e-9, position.distanceTo(relativeEnd));
            Optional<Vec3> obstacle = world.obstruction(position, next);
            if (obstacle.isPresent() && (relativeHit.isEmpty() || position.distanceTo(obstacle.get()) <= velocity.length() * fraction + 1e-5)) return -1;
            if (relativeHit.isPresent()) return tick + fraction;
            position = next; velocity = velocity.scale(DRAG).add(0, -GRAVITY, 0);
        }
        return -1;
    }
    static double speedForCharge(int ticks) { double t = Math.min(1, Math.max(0, ticks) / 20.0); return 3 * Math.min(1, (t * t + t * 2) / 3); }
    private static boolean finite(Vec3 v) { return Double.isFinite(v.x) && Double.isFinite(v.y) && Double.isFinite(v.z); }
    private BowTrajectory() {}
}
