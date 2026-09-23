package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

final class GuardParkingPolicyTest {
    @Test void onlyVerifiedHighHoverKeepsTheClientOnline(){
        assertTrue(GuardParkingPolicy.ready(100.5,95,200.5,100.5,95,200.5,65,20,true,true));
        assertFalse(GuardParkingPolicy.ready(100.5,75,200.5,100.5,75,200.5,65,20,true,true));
        assertTrue(GuardParkingPolicy.ready(107.5,95,200.5,100.5,95,200.5,65,20,true,true));
        assertFalse(GuardParkingPolicy.ready(109.5,95,200.5,100.5,95,200.5,65,20,true,true));
        assertFalse(GuardParkingPolicy.ready(100.5,95,200.5,100.5,95,200.5,65,17,true,true));
        assertFalse(GuardParkingPolicy.ready(100.5,95,200.5,100.5,95,200.5,65,20,false,true));
        assertFalse(GuardParkingPolicy.ready(100.5,95,200.5,100.5,95,200.5,65,20,true,false));
    }
}
