package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GuardEscapePolicyTest {
    @Test void onlyExactLiveMaterialLeaseCanPreemptCombat() {
        assertTrue(GuardEscapePolicy.currentLease("world-a",11,"world-a",11,"world-a",10,"job-a","job-a"));
        assertFalse(GuardEscapePolicy.currentLease("world-b",11,"world-a",11,"world-a",10,"job-a","job-a"));
        assertFalse(GuardEscapePolicy.currentLease("world-a",11,"world-a",10,"world-a",10,"job-a","job-a"));
        assertFalse(GuardEscapePolicy.currentLease("world-a",11,"world-a",11,"world-a",9,"job-a","job-a"));
        assertFalse(GuardEscapePolicy.currentLease("world-a",11,"world-a",11,"world-a",10,"job-a","job-b"));
    }
    @Test void onlyOwnedVerticalRiseCanInterruptDefense() {
        assertTrue(GuardEscapePolicy.allowed(true,true,10,63,20,10.5,85,20.5));
        assertFalse(GuardEscapePolicy.allowed(false,true,10,63,20,10,85,20));
        assertFalse(GuardEscapePolicy.allowed(true,false,10,63,20,10,85,20));
        assertFalse(GuardEscapePolicy.allowed(true,true,10,63,20,15,85,20));
        assertFalse(GuardEscapePolicy.allowed(true,true,10,63,20,10,64,20));
        assertTrue(GuardEscapePolicy.allowed(true,true,10,63,20,10,65,20));
        assertFalse(GuardEscapePolicy.allowed(true,true,10,63,20,10,130,20));
    }

    @Test void underwaterAirReturnPreemptsCombatOnlyInAProvenColumn() {
        assertTrue(GuardEscapePolicy.underwaterAirReturn(
            true,true,true,true,10.5,52,20.5,10.5,65,20.5,63));
        assertTrue(GuardEscapePolicy.underwaterAirReturn(
            true,true,true,true,10.5,65,20.5,10.5,85,20.5,63));
        assertFalse(GuardEscapePolicy.underwaterAirReturn(
            true,true,true,false,10.5,52,20.5,10.5,65,20.5,63));
        assertFalse(GuardEscapePolicy.underwaterAirReturn(
            true,true,false,true,10.5,52,20.5,10.5,65,20.5,63));
        assertFalse(GuardEscapePolicy.underwaterAirReturn(
            true,true,true,true,10.5,52,20.5,12,65,20.5,63));
        assertFalse(GuardEscapePolicy.underwaterAirReturn(
            true,true,true,true,10.5,52,20.5,10.75,65,20.5,63));
        assertFalse(GuardEscapePolicy.underwaterAirReturn(
            true,true,true,true,10.5,52,20.5,10.5,63,20.5,63));
    }
}
