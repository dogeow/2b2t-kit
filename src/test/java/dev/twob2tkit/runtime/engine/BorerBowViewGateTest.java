package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim.Look;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerBowViewGateTest {
    @Test void assignedPlayerRotationWithoutRenderedCameraNeverAuthorizesRelease() {
        var gate = new BorerBowViewGate(); var look = new Look(90, -5);
        assertFalse(gate.ready(look, look, 10));
        gate.rendered(look, 10); assertTrue(gate.ready(look, look, 11));
    }
    @Test void bothLastVisibleFrameAndCurrentCameraMustFaceTheShot() {
        var gate = new BorerBowViewGate(); var look = new Look(90, -5); var away = new Look(0, 0);
        gate.rendered(away, 10); assertFalse(gate.ready(look, look, 11));
        gate.rendered(look, 10); assertFalse(gate.ready(look, away, 11));
    }
    @Test void staleFramesAndClockResetCannotAuthorizeRelease() {
        var gate = new BorerBowViewGate(); var look = new Look(90, -5);
        gate.rendered(look, 10);
        assertFalse(gate.ready(look, look, 13)); assertFalse(gate.ready(look, look, 0));
    }
    @Test void cancelOrTargetChangeRequiresANewVisibleFrame() {
        var gate = new BorerBowViewGate(); var look = new Look(90, -5);
        gate.rendered(look, 10); gate.reset(); assertFalse(gate.ready(look, look, 10));
    }
    @Test void yawWrapAndSmallPredictionUpdatesAreAllowedButLargeChangesAreNot() {
        assertTrue(BorerBowViewGate.aligned(new Look(179.5F, -5), new Look(-179.5F, -4)));
        assertTrue(BorerBowViewGate.aligned(new Look(90, -5), new Look(95, -5)), "Do not deadlock a nearby strafing skeleton");
        assertFalse(BorerBowViewGate.aligned(new Look(90, -5), new Look(97, -5)));
        assertFalse(BorerBowViewGate.aligned(new Look(90, -5), new Look(90, -12)));
    }
    @Test void invalidCameraNeverAuthorizesRelease() {
        assertFalse(BorerBowViewGate.aligned(new Look(0, 0), new Look(Float.NaN, 0)));
        assertFalse(BorerBowViewGate.aligned(null, new Look(0, 0)));
    }
}
