package dev.twob2tkit.chopper;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ChopperStandbyPolicyTest {
    @Test void restoredHoverDoesNotStartAnotherLandingLoop(){
        assertTrue(ChopperStandbyPolicy.arrived(true,.018,0,-.0196));
        assertTrue(ChopperStandbyPolicy.arrived(true,.002,0,0));
        assertFalse(ChopperStandbyPolicy.arrived(false,.018,0,-.0196));
        assertFalse(ChopperStandbyPolicy.arrived(true,.05,0,-.0196));
        assertFalse(ChopperStandbyPolicy.arrived(true,.018,.2,-.0196));
        assertFalse(ChopperStandbyPolicy.arrived(true,.018,0,-.3));
    }
}
