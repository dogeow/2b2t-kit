package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class WaterDescentPolicyTest {
    @Test void boundedPickupAndAirReserve() {
        assertTrue(WaterDescentPolicy.allowed(true,true,true,20,270,.2,2));
        assertFalse(WaterDescentPolicy.allowed(true,true,true,20,259,.2,2));
        assertTrue(WaterDescentPolicy.allowed(true,true,true,20,270,.8,2));
        assertFalse(WaterDescentPolicy.allowed(true,true,true,20,270,1.6,2));
        assertFalse(WaterDescentPolicy.allowed(true,true,true,20,270,.2,6));
        assertTrue(WaterDescentPolicy.continueDescent(true,20,245));
        assertFalse(WaterDescentPolicy.continueDescent(true,20,244));
        assertFalse(WaterDescentPolicy.atTarget(53,52));
        assertTrue(WaterDescentPolicy.atTarget(52.2,52));
        assertTrue(WaterDescentPolicy.sink(53,52));
        assertFalse(WaterDescentPolicy.sink(52.1,52));
        assertTrue(WaterDescentPolicy.align(.66));
        assertFalse(WaterDescentPolicy.align(.1));
    }
}
