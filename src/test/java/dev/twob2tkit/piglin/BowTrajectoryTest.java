package dev.twob2tkit.piglin;

import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import java.util.Optional;
import static org.junit.jupiter.api.Assertions.*;

class BowTrajectoryTest {
    private static final Vec3 ORIGIN = new Vec3(0, 1.52, 0);
    private static final BowTrajectory.World CLEAR = (from, to) -> Optional.empty();
    private static AABB body(double x, double y, double z) { return new AABB(x - .3, y, z - .3, x + .3, y + 1.99, z + .3); }
    private static BowTrajectory.Solution solve(AABB body, Vec3 motion, Vec3 inherited, double latency) {
        return BowTrajectory.solve(ORIGIN, inherited, body, motion, latency, 3, CLEAR);
    }
    /** Independent tiny-step integration checks the physical body, with no inflated hitbox or fixed future box. */
    private static void assertIntercept(BowTrajectory.Solution shot, AABB body, Vec3 motion, Vec3 inherited, double latency) {
        assertNotNull(shot);
        assertEquals(1, shot.direction().length(), 1e-8);
        Vec3 arrow = ORIGIN, velocity = shot.direction().scale(3).add(inherited);
        for (int tick = 0; tick < 100; tick++) {
            for (int part = 0; part <= 200; part++) {
                double t = part / 200.0;
                if (body.move(motion.scale(tick + t + latency)).contains(arrow.add(velocity.scale(t)))) return;
            }
            arrow = arrow.add(velocity);
            velocity = new Vec3(velocity.x * .99, velocity.y * .99 - .05, velocity.z * .99);
        }
        fail("Arrow never intersected the moving body");
    }
    @Test void stationaryTargetsAtDifferentRangesAndHeights() {
        for (double range : new double[]{4, 12, 25, 40}) for (double y : new double[]{-8, 0, 6}) {
            AABB body = body(0, y, range);
            assertIntercept(solve(body, Vec3.ZERO, Vec3.ZERO, 0), body, Vec3.ZERO, Vec3.ZERO, 0);
        }
    }
    @Test void leadsStrafingSkeletonInBothDirections() {
        for (double vx : new double[]{-.22, .22}) {
            AABB body = body(0, 0, 28); Vec3 motion = new Vec3(vx, 0, 0);
            var shot = solve(body, motion, Vec3.ZERO, 0);
            assertIntercept(shot, body, motion, Vec3.ZERO, 0);
            assertEquals(Math.signum(vx), Math.signum(shot.direction().x));
            assertTrue(Math.abs(shot.predictedCenter().x) > 1);
        }
    }
    @Test void handlesApproachingAndRecedingSkeleton() {
        for (double vz : new double[]{-.25, .25}) {
            AABB body = body(3, 0, 30); Vec3 motion = new Vec3(0, 0, vz);
            assertIntercept(solve(body, motion, Vec3.ZERO, 0), body, motion, Vec3.ZERO, 0);
        }
    }
    @Test void compensatesShooterStrafeAndFlyingVelocity() {
        AABB body = body(0, 0, 26); Vec3 motion = new Vec3(-.15, 0, 0);
        for (Vec3 inherited : new Vec3[]{new Vec3(.35, 0, 0), new Vec3(0, .3, -.2), new Vec3(-.4, -.25, .2)})
            assertIntercept(solve(body, motion, inherited, 0), body, motion, inherited, 0);
    }
    @Test void latencyAddsBoundedLead() {
        AABB body = body(0, 0, 25); Vec3 motion = new Vec3(.2, 0, 0);
        var noDelay = solve(body, motion, Vec3.ZERO, 0);
        var delayed = solve(body, motion, Vec3.ZERO, 3);
        assertIntercept(delayed, body, motion, Vec3.ZERO, 3);
        assertTrue(delayed.direction().x > noDelay.direction().x);
        assertEquals(solve(body, motion, Vec3.ZERO, 4), solve(body, motion, Vec3.ZERO, 50));
    }
    @Test void doesNotShootThroughWallOrInterveningEntity() {
        AABB wall = new AABB(-20, -20, 9, 20, 20, 10);
        BowTrajectory.World blocked = wall::clip;
        assertNull(BowTrajectory.solve(ORIGIN, Vec3.ZERO, body(0, 0, 20), Vec3.ZERO, 0, 3, blocked));
        AABB otherPlayer = new AABB(-.5, 0, 9, .5, 2.5, 10);
        assertNull(BowTrajectory.solve(ORIGIN, Vec3.ZERO, body(0, 0, 20), Vec3.ZERO, 0, 3, otherPlayer::clip));
    }
    @Test void obstacleBeyondTargetDoesNotCancelAHit() {
        AABB wall = new AABB(-20, -20, 26, 20, 20, 27);
        assertNotNull(BowTrajectory.solve(ORIGIN, Vec3.ZERO, body(0, 0, 20), Vec3.ZERO, 0, 3, wall::clip));
    }
    @Test void movingBoxCannotBeReplacedByAStaticPredictedBox() {
        AABB initial = body(2, 0, 12);
        var boxes = BowTrajectory.forecast(initial, new Vec3(.8, 0, 0), 0, CLEAR);
        // This arrow crosses the original position after the mob has already moved away.
        assertEquals(-1, BowTrajectory.hitTime(ORIGIN, initial.getCenter().subtract(ORIGIN).normalize().scale(3), boxes, CLEAR));
        assertIntercept(solve(initial, new Vec3(.8, 0, 0), Vec3.ZERO, 0), initial, new Vec3(.8, 0, 0), Vec3.ZERO, 0);
    }
    @Test void targetForecastStopsAtWallButKeepsSliding() {
        BowTrajectory.World wall = new BowTrajectory.World() {
            public Optional<Vec3> obstruction(Vec3 a, Vec3 b) { return Optional.empty(); }
            public boolean targetSpace(AABB box) { return box.maxX <= 1.31; }
        };
        var boxes = BowTrajectory.forecast(body(0, 0, 20), new Vec3(.2, 0, .1), 0, wall);
        assertTrue(boxes[50].maxX <= 1.31);
        assertEquals(boxes[20].minX, boxes[50].minX);
        assertEquals(3, boxes[50].minZ - boxes[20].minZ, 1e-8);
    }
    @Test void rejectsImpossibleOrNonFiniteTrajectoryAndEmptyCharge() {
        assertNull(solve(body(0, 0, 1000), Vec3.ZERO, Vec3.ZERO, 0));
        assertNull(BowTrajectory.solve(ORIGIN, Vec3.ZERO, body(0, 0, 20), Vec3.ZERO, 0, 0, CLEAR));
        assertNull(solve(body(0, 0, 20), new Vec3(Double.NaN, 0, 0), Vec3.ZERO, 0));
        assertEquals(3, BowTrajectory.speedForCharge(20));
        assertEquals(3, BowTrajectory.speedForCharge(100));
        assertEquals(1.25, BowTrajectory.speedForCharge(10));
    }
}
