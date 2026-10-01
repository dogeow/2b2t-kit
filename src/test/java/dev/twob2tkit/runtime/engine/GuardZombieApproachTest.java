package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import net.minecraft.world.phys.Vec3;

import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class GuardZombieApproachTest {
    private static final UUID ZOMBIE = UUID.fromString("00000000-0000-0000-0000-000000000001");

    @Test void sprintAndNormalFlightStayInsideTheCheckedShortStep() {
        var input = BorerFlyPath.input(Vec3.ZERO, new Vec3(3, 0, 0), 0);
        assertEquals(.2, input.delta().length(), 1e-9);
        double speed = GuardZombieApproach.sprintSafeSpeed(input.speed());
        for (int multiplier : new int[]{10, 15}) {
            assertTrue(speed * multiplier <= input.delta().length(),
                "Actual flight step must stay inside the collision-checked sweep");
            assertTrue(speed * multiplier <= .2);
        }
    }

    @Test void approachesThreeBlockZombieInShortBoundedStepsThenAttacks() {
        var approach = new GuardZombieApproach();
        for (int tick = 0; tick < 12; tick++) {
            double x = tick * .2;
            var step = approach.step(ZOMBIE, tick, x, 0, 3, 0,
                false, true, true);
            assertEquals(GuardZombieApproach.Decision.MOVE, step.decision());
        }
        assertEquals(GuardZombieApproach.Decision.ATTACK,
            approach.step(ZOMBIE, 12, 2.4, 0, 3, 0, true, true, true).decision());
    }

    @Test void formerThreePointSixBlockFallbackNowApproachesThenKeepsSafeMeleeAvailable() {
        var approach = new GuardZombieApproach();
        for(int tick=0;tick<30;tick++)
            assertEquals(GuardZombieApproach.Decision.MOVE,
                approach.step(ZOMBIE,tick,tick*.2,0,7,0,false,true,true).decision());
        assertEquals(GuardZombieApproach.Decision.ATTACK,
            approach.step(ZOMBIE,200,6.8,0,7,0,true,true,true).decision());
    }
    @Test void unsafeHeightOrBlockedStepCancelsWithoutMovement() {
        var approach = new GuardZombieApproach();
        assertEquals("unsafe_height", approach.step(ZOMBIE, 0, 0, 0, 2.5, 0,
            false, false, true).reason());
        approach.reset();
        assertEquals("path_blocked", approach.step(ZOMBIE, 1, 0, 0, 2.5, 0,
            false, true, false).reason());
        assertEquals("retry_cooldown", approach.step(ZOMBIE, 2, 0, 0, 2.5, 0,
            false, true, true).reason());
    }

    @Test void distanceStallAndTravelCapsStopPursuit() {
        var approach = new GuardZombieApproach();
        assertEquals("target_out_of_range", approach.step(ZOMBIE, 0, 0, 0, 10, 0,
            false, true, true).reason());
        approach.reset();
        assertEquals(GuardZombieApproach.Decision.MOVE, approach.step(ZOMBIE, 1, 0, 0, 3, 0,
            false, true, true).decision());
        assertEquals("stalled", approach.step(ZOMBIE, 22, 0, 0, 3, 0,
            false, true, true).reason());
        approach.reset();
        approach.step(ZOMBIE, 23, 0, 0, 3, 0, false, true, true);
        assertEquals("travel_limit", approach.step(ZOMBIE, 24, 8.6, 0, 3, 0,
            false, true, true).reason());
    }
}
