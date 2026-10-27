package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class DryRoofMiningPolicyTest {
    @Test void unchangedSourceBelowAnOwnedDryRockTargetIsAllowed() {
        assertNull(DryRoofMiningPolicy.rejection(true,true,true,true,false,false,false,true));
    }
    @Test void sideUpperFlowingOrLavaFluidCannotUseThisException() {
        assertNotNull(DryRoofMiningPolicy.rejection(true,true,true,true,true,false,false,true));
        assertNotNull(DryRoofMiningPolicy.rejection(true,true,true,false,false,false,false,true));
    }
    @Test void ownershipHealthAirAndNaturalTargetRemainMandatory() {
        assertNotNull(DryRoofMiningPolicy.rejection(false,true,true,true,false,false,false,true));
        assertNotNull(DryRoofMiningPolicy.rejection(true,false,true,true,false,false,false,true));
        assertNotNull(DryRoofMiningPolicy.rejection(true,true,false,true,false,false,false,true));
    }
    @Test void supportFallingBlocksAndToolReserveRemainProtected() {
        assertNotNull(DryRoofMiningPolicy.rejection(true,true,true,true,false,true,false,true));
        assertNotNull(DryRoofMiningPolicy.rejection(true,true,true,true,false,false,true,true));
        assertNotNull(DryRoofMiningPolicy.rejection(true,true,true,true,false,false,false,false));
    }
}
