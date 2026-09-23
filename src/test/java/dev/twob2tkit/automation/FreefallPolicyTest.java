package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class FreefallPolicyTest {
    @Test void onlyLongGuardedFallsAreEligible(){
        assertTrue(FreefallPolicy.eligible(215,106,20,true,true));
        assertFalse(FreefallPolicy.eligible(125,106,20,true,true));
        assertFalse(FreefallPolicy.eligible(215,106,17,true,true));
        assertFalse(FreefallPolicy.eligible(215,106,20,false,true));
    }
    @Test void brakingStartsWellAboveTheRequestedHeight(){
        assertFalse(FreefallPolicy.brake(125,106,20,false));
        assertTrue(FreefallPolicy.brake(122,106,20,false));
        assertTrue(FreefallPolicy.brake(180,106,20,true));
    }
}
