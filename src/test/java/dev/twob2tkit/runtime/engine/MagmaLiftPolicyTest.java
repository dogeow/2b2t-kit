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
    @Test void liftThatNeverRisesIsDetectedAsStalledAndRiseResetsIt() {
        int ticks = 0;
        for (int i = 0; i < MagmaLiftPolicy.STALL_LIMIT_TICKS - 1; i++) ticks = MagmaLiftPolicy.nextStall(ticks, 31.0, 31.0);
        assertFalse(MagmaLiftPolicy.stalled(ticks));
        ticks = MagmaLiftPolicy.nextStall(ticks, 31.0, 31.0);
        assertTrue(MagmaLiftPolicy.stalled(ticks));
        assertEquals(0, MagmaLiftPolicy.nextStall(ticks, 31.0, 31.2));
    }
    @Test void flyingOnMagmaMustLandBeforeSneakCanProtect() {
        assertTrue(MagmaLiftPolicy.mustLandToSneak(true, true));
        assertFalse(MagmaLiftPolicy.mustLandToSneak(false, true));
        assertFalse(MagmaLiftPolicy.mustLandToSneak(true, false));
    }
}
