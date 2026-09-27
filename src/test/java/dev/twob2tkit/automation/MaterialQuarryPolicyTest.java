package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MaterialQuarryPolicyTest {
    @Test void rejectsUnboundedSameHeightCornersAndOversizedAreas() {
        assertTrue(MaterialQuarryPolicy.bounds(8,6,8,200));
        assertFalse(MaterialQuarryPolicy.bounds(8,1,8,20));
        assertFalse(MaterialQuarryPolicy.bounds(17,6,8,20));
        assertFalse(MaterialQuarryPolicy.bounds(8,13,8,20));
        assertFalse(MaterialQuarryPolicy.bounds(8,6,8,0));
    }
    @Test void onlySandAndAirMayBeExcavatedAndTheBufferMustBeDry() {
        assertTrue(MaterialQuarryPolicy.cellAllowed(true,true,false,true,false,false));
        assertTrue(MaterialQuarryPolicy.cellAllowed(true,true,true,false,false,false));
        assertFalse(MaterialQuarryPolicy.cellAllowed(true,true,false,false,false,false));
        assertFalse(MaterialQuarryPolicy.cellAllowed(true,false,true,false,true,false));
        assertFalse(MaterialQuarryPolicy.cellAllowed(true,false,false,false,false,true));
        assertFalse(MaterialQuarryPolicy.cellAllowed(false,true,true,false,false,false));
    }
}
