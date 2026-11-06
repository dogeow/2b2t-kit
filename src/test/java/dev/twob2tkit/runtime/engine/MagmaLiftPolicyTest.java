package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MagmaLiftPolicyTest {
    @Test void flightAndCrouchCannotCancelEachOther() {
        assertTrue(MagmaLiftPolicy.input(true).jump());
        assertFalse(MagmaLiftPolicy.input(true).sneak());
        assertFalse(MagmaLiftPolicy.input(false).jump());
        assertTrue(MagmaLiftPolicy.input(false).sneak());
    }
    @Test void blockedUnloadedOrWetHeadroomNeverQualifiesForLift() {
        assertTrue(MagmaLiftPolicy.hasClearance(true,true,true));
        assertFalse(MagmaLiftPolicy.hasClearance(false,true,true));
        assertFalse(MagmaLiftPolicy.hasClearance(true,false,true));
        assertFalse(MagmaLiftPolicy.hasClearance(true,true,false));
    }
}
