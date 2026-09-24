package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GuardEscapePolicyTest {
    @Test void onlyOwnedVerticalRiseCanInterruptDefense() {
        assertTrue(GuardEscapePolicy.allowed(true,true,10,63,20,10.5,85,20.5));
        assertFalse(GuardEscapePolicy.allowed(false,true,10,63,20,10,85,20));
        assertFalse(GuardEscapePolicy.allowed(true,false,10,63,20,10,85,20));
        assertFalse(GuardEscapePolicy.allowed(true,true,10,63,20,15,85,20));
        assertFalse(GuardEscapePolicy.allowed(true,true,10,63,20,10,64,20));
        assertTrue(GuardEscapePolicy.allowed(true,true,10,63,20,10,65,20));
        assertFalse(GuardEscapePolicy.allowed(true,true,10,63,20,10,130,20));
    }
}
