package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AutoRefillCompatibilityTest {
    @Test void noKitOwnerDoesNotSuppressOrdinaryAutoRefill(){
        var hooks=new AutoRefillCompatibility.Observation();assertFalse(hooks.tick(false,100));
        var state=hooks.snapshot(true,false,101);
        assertTrue(state.get("hook_seen").getAsBoolean());assertTrue(state.get("supported").getAsBoolean());
        assertFalse(state.get("active").getAsBoolean());assertFalse(state.get("suppressed").getAsBoolean());
        assertEquals(0,state.get("suppressed_ticks").getAsLong());
    }
    @Test void theWholeOwnedWindowSuppressesRefillAndCursorCleanup(){
        var hooks=new AutoRefillCompatibility.Observation();
        assertTrue(hooks.tick(true,100));assertTrue(hooks.tick(true,150));
        var state=hooks.snapshot(true,true,200);assertTrue(state.get("suppressed").getAsBoolean());
        assertEquals(2,state.get("suppressed_ticks").getAsLong());assertEquals(150,state.get("last_suppressed_at").getAsLong());
        assertFalse(hooks.tick(false,250));assertFalse(hooks.snapshot(true,false,251).get("suppressed").getAsBoolean());
    }
    @Test void priorSuppressionCannotProveFreshCurrentOwnership(){
        var hooks=new AutoRefillCompatibility.Observation();hooks.tick(true,100);
        assertFalse(hooks.snapshot(true,true,1101).get("suppressed").getAsBoolean());
        assertFalse(hooks.snapshot(true,false,101).get("suppressed").getAsBoolean());
        hooks.tick(false,102);assertFalse(hooks.snapshot(true,true,103).get("suppressed").getAsBoolean());
    }
    @Test void anAbsentOptionalModNeedsNoHookAndAnUnseenPresentModCannotPass(){
        var hooks=new AutoRefillCompatibility.Observation();
        assertTrue(hooks.snapshot(false,true,100).get("supported").getAsBoolean());
        assertFalse(hooks.snapshot(false,true,100).get("suppressed").getAsBoolean());
        assertFalse(hooks.snapshot(true,true,100).get("supported").getAsBoolean());
    }
}
