package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class MapCreationPolicyTest {
    @Test void fullInventoryAllowsOnlyTheHeldSingleMapReplacement() {
        assertTrue(MapCreationPolicy.canReceive(1,0));
        assertTrue(MapCreationPolicy.canReceive(32,1));
        assertFalse(MapCreationPolicy.canReceive(32,0));
        assertFalse(MapCreationPolicy.canReceive(0,1));
    }
    @Test void oneConsumptionAndExactlyOneNewIdConfirmCreationIncludingIdZero() {
        assertEquals(0,MapCreationPolicy.confirmedId(1,0,Map.of(),Map.of(0,1)));
        assertEquals(81,MapCreationPolicy.confirmedId(32,31,Map.of(20,2),Map.of(20,2,81,1)));
    }
    @Test void oldMapTransfersCountChangesAndAmbiguousNewIdsCannotConfirm() {
        assertEquals(-1,MapCreationPolicy.confirmedId(1,1,Map.of(),Map.of(1,1)));
        assertEquals(-1,MapCreationPolicy.confirmedId(2,0,Map.of(),Map.of(1,1)));
        assertEquals(-1,MapCreationPolicy.confirmedId(1,0,Map.of(1,1),Map.of(1,2)));
        assertEquals(-1,MapCreationPolicy.confirmedId(1,0,Map.of(1,1),Map.of(2,1)));
        assertEquals(-1,MapCreationPolicy.confirmedId(1,0,Map.of(),Map.of(1,1,2,1)));
        assertEquals(-1,MapCreationPolicy.confirmedId(1,0,Map.of(),Map.of(1,2)));
    }
    @Test void scaleZeroGridUsesTheActualNegativeAndPositiveBoundaryRule() {
        assertEquals(0,MapCreationPolicy.scaleZeroCenter(-64));
        assertEquals(-128,MapCreationPolicy.scaleZeroCenter(-64.01));
        assertEquals(0,MapCreationPolicy.scaleZeroCenter(63.99));
        assertEquals(128,MapCreationPolicy.scaleZeroCenter(64));
        assertEquals(761088,MapCreationPolicy.scaleZeroCenter(761088.5));
        assertEquals(797696,MapCreationPolicy.scaleZeroCenter(797696.5));
        assertThrows(IllegalArgumentException.class,()->MapCreationPolicy.scaleZeroCenter(Double.NaN));
    }
}
