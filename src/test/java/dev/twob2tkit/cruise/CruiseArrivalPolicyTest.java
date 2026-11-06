package dev.twob2tkit.cruise;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CruiseArrivalPolicyTest {
    @Test void manualArrivalNeverInheritsAnInvalidScriptRadius() {
        assertEquals(1.0, CruiseArrivalPolicy.manualRadius(.25));
        assertEquals(8.0, CruiseArrivalPolicy.manualRadius(Double.NaN));
        assertEquals(8.0, CruiseArrivalPolicy.manualRadius(8.0));
        assertEquals(128.0, CruiseArrivalPolicy.manualRadius(500.0));
    }

    @Test void scriptRadiusNeverChangesTheUsersConfiguredRadius() {
        assertEquals(.25, CruiseArrivalPolicy.scriptRadius(true, .25, 8.0));
        assertEquals(8.0, CruiseArrivalPolicy.scriptRadius(false, .25, 8.0));
    }

    @Test void manualFlightRecognizesCrossingTheDestinationBetweenTicks() {
        assertTrue(CruiseArrivalPolicy.reached(false, -2, 0, 2, 0, 0, 0, 1));
        assertFalse(CruiseArrivalPolicy.reached(false, -2, 2, 2, 2, 0, 0, 1));
        assertFalse(CruiseArrivalPolicy.reached(false, -20, 0, 20, 0, 0, 0, 1));
        assertFalse(CruiseArrivalPolicy.reached(false, Double.NaN, 0, 2, 0, 0, 0, 1));
    }

    @Test void exactTasksRequireActualPositionWithinTheirRequestedRadius() {
        assertFalse(CruiseArrivalPolicy.reached(true, -2, 0, 2, 0, 0, 0, .25));
        assertTrue(CruiseArrivalPolicy.reached(true, -2, 0, .2, 0, 0, 0, .25));
        assertFalse(CruiseArrivalPolicy.reached(true, 0, 0, Double.NaN, 0, 0, 0, .25));
    }
}
