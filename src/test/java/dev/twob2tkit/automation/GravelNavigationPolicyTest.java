package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GravelNavigationPolicyTest {
    @Test void aboveWaterTransitUsesPreciseNavigationIncludingArrivalDrift() {
        for (String stage : new String[]{"SETTLE_HIGH", "SETTLE_SURFACE", "PARK", "REFILL"}) {
            assertTrue(GravelNavigationPolicy.dryTransit(stage, false, 89.5, 66, 65));
            assertTrue(GravelNavigationPolicy.dryTransit(stage, false, 64.81, 65, 65));
        }
    }

    @Test void underwaterOrLowBodyRetainsTheExistingWaterRoute() {
        assertFalse(GravelNavigationPolicy.dryTransit("REFILL", true, 52, 65, 65));
        assertFalse(GravelNavigationPolicy.dryTransit("REFILL", false, 64, 65, 65));
        assertFalse(GravelNavigationPolicy.dryTransit("SETTLE_HIGH", false, 66, 52, 65));
    }

    @Test void DivingMiningAndPickupAreNeverDryTransit() {
        for (String stage : new String[]{"SETTLE_DIVE", "HOVER", "STAND", "MINE", "DROP", "PICKUP", "VERIFY"}) {
            assertFalse(GravelNavigationPolicy.dryTransit(stage, false, 89, 88, 65));
        }
    }

    @Test void InvalidStageAndHeightCannotClaimDryNavigation() {
        assertFalse(GravelNavigationPolicy.dryTransit(null, false, 89, 88, 65));
        assertFalse(GravelNavigationPolicy.dryTransit("OTHER", false, 89, 88, 65));
        assertFalse(GravelNavigationPolicy.dryTransit("PARK", false, Double.NaN, 88, 65));
        assertFalse(GravelNavigationPolicy.dryTransit("PARK", false, 89, Double.POSITIVE_INFINITY, 65));
        assertFalse(GravelNavigationPolicy.dryTransit("PARK", false, 89, 88, Double.NaN));
    }
}
