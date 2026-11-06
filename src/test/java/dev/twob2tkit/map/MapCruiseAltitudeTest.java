package dev.twob2tkit.map;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MapCruiseAltitudeTest {
    @Test void mapRouteNeverTargetsOrDodgesBelowItsClickTimeHeight() {
        assertEquals(185.25, MapCruiseAltitude.floor(100.0, 185.25));
        assertEquals(200.0, MapCruiseAltitude.floor(200.0, 185.25));
        assertFalse(MapCruiseAltitude.permits(182.25, 185.25));
        assertTrue(MapCruiseAltitude.permits(185.25, 185.25));
        assertTrue(MapCruiseAltitude.permits(190.0, 185.25));
        assertEquals(-20.5, MapCruiseAltitude.floor(-40.0, -20.5));
    }

    @Test void ordinaryRoutesRetainTheirExistingAltitudeAndDodgePolicy() {
        assertEquals(100.0, MapCruiseAltitude.floor(100.0, Double.NaN));
        assertTrue(MapCruiseAltitude.permits(90.0, Double.NaN));
    }
}
