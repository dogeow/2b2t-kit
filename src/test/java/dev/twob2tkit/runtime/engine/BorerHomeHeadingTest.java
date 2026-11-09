package dev.twob2tkit.runtime.engine;

import net.minecraft.core.Direction;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerHomeHeadingTest {
    @Test void levelOnTheCurrentAxisTurnsTowardTheSidewaysGoal() {
        // 2026-11-02: facing EAST with the home point 0.09 east and 0.76 north stalled at "回家通道被挡".
        assertEquals(Direction.NORTH, BorerHome.homeHeading(Direction.EAST, 0.09, -0.76));
        assertEquals(Direction.SOUTH, BorerHome.homeHeading(Direction.WEST, -0.1, 0.5));
        assertEquals(Direction.EAST, BorerHome.homeHeading(Direction.NORTH, 0.6, 0.05));
        assertEquals(Direction.WEST, BorerHome.homeHeading(Direction.SOUTH, -0.6, -0.15));
    }
    @Test void hysteresisStillKeepsTheCurrentAxisWhileItIsClearlyProgressing() {
        assertEquals(Direction.EAST, BorerHome.homeHeading(Direction.EAST, 2.0, -2.5));
        assertEquals(Direction.NORTH, BorerHome.homeHeading(Direction.NORTH, 2.5, -2.0));
        assertEquals(Direction.WEST, BorerHome.homeHeading(Direction.EAST, -1.0, 0.2));
    }
    @Test void farOffAxisGoalSwitchesAndArrivalKeepsTheHeading() {
        assertEquals(Direction.SOUTH, BorerHome.homeHeading(Direction.EAST, 0.5, 4.0));
        assertEquals(Direction.EAST, BorerHome.homeHeading(Direction.EAST, 0.1, 0.1));
        assertEquals(Direction.EAST, BorerHome.homeHeading(Direction.WEST, 3.0, 0.0));
    }
}
