package dev.twob2tkit.piglin;

import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BowTargetMotionTest {
    @Test void measuresRemoteMobDespiteZeroDeltaMovement() {
        var tracker = new BowTargetMotion();
        tracker.observe(10, Vec3.ZERO, Vec3.ZERO, true);
        assertEquals(.2, tracker.observe(11, new Vec3(.2, 0, 0), Vec3.ZERO, true).x, 1e-8);
        assertEquals(.2, tracker.observe(13, new Vec3(.6, 0, 0), Vec3.ZERO, true).x, 1e-8);
    }
    @Test void duplicateSolveWithinOneTickDoesNotEraseVelocity() {
        var tracker = new BowTargetMotion();
        tracker.observe(0, Vec3.ZERO, Vec3.ZERO, true);
        var velocity = tracker.observe(1, new Vec3(.2, 0, 0), Vec3.ZERO, true);
        assertEquals(velocity, tracker.observe(1, new Vec3(.2, 0, 0), Vec3.ZERO, true));
    }
    @Test void reversingAndTurningReactImmediately() {
        var tracker = new BowTargetMotion();
        tracker.observe(0, Vec3.ZERO, new Vec3(.2, 0, 0), true);
        assertEquals(-.2, tracker.observe(1, new Vec3(-.2, 0, 0), Vec3.ZERO, true).x, 1e-8);
        assertEquals(new Vec3(0, 0, .2), tracker.observe(2, new Vec3(-.2, 0, .2), Vec3.ZERO, true));
    }
    @Test void stoppedMobDoesNotRetainOldLead() {
        var tracker = new BowTargetMotion();
        tracker.observe(0, Vec3.ZERO, new Vec3(.2, 0, 0), true);
        assertEquals(.05, tracker.observe(1, Vec3.ZERO, Vec3.ZERO, true).x, 1e-8);
        assertEquals(Vec3.ZERO, tracker.observe(2, Vec3.ZERO, Vec3.ZERO, true));
    }
    @Test void teleportStaleSampleAndWorldClockResetDoNotProduceHugeLead() {
        var tracker = new BowTargetMotion();
        tracker.observe(100, Vec3.ZERO, Vec3.ZERO, true);
        assertEquals(Vec3.ZERO, tracker.observe(101, new Vec3(100, 0, 0), Vec3.ZERO, true));
        assertEquals(Vec3.ZERO, tracker.observe(120, new Vec3(120, 0, 0), Vec3.ZERO, true));
        assertEquals(Vec3.ZERO, tracker.observe(0, Vec3.ZERO, Vec3.ZERO, true));
    }
    @Test void clampsSpeedAndRejectsInvalidData() {
        var tracker = new BowTargetMotion();
        var velocity = tracker.observe(0, Vec3.ZERO, new Vec3(4, 3, 0), true);
        assertEquals(.8, velocity.x, 1e-8); assertEquals(0, velocity.y);
        assertEquals(Vec3.ZERO, tracker.observe(1, new Vec3(Double.NaN, 0, 0), Vec3.ZERO, true));
    }
}
