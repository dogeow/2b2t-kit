package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LootClearancePolicyTest {
    @Test void sameValidBlockCanKeepItsMiningProgress() {
        for(int tick=0;tick<200;tick++) {
            assertFalse(LootClearancePolicy.clearBeforePickup(true,false,false,false));
            assertTrue(LootClearancePolicy.keepTarget(true,true));
        }
        assertFalse(LootClearancePolicy.keepTarget(false,true));
        assertFalse(LootClearancePolicy.keepTarget(true,false));
    }
    @Test void clearanceIsReleasedOnlyWhenPickupNoLongerNeedsIt() {
        assertTrue(LootClearancePolicy.clearBeforePickup(false,true,false,false));
        assertFalse(LootClearancePolicy.clearBeforePickup(true,false,false,false));
        assertFalse(LootClearancePolicy.clearBeforePickup(false,true,true,false));
        assertFalse(LootClearancePolicy.clearBeforePickup(false,true,false,true));
    }
}
