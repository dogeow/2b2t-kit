package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class AutomationScopeTest {
    @Test void defaultPortIsEquivalentButAnotherDestinationIsNot(){
        assertTrue(AutomationScope.sameServer("Simpcraft.com:25565","simpcraft.com"));
        assertFalse(AutomationScope.sameServer("simpcraft.com:25566","simpcraft.com"));
        assertFalse(AutomationScope.sameServer("other.example","simpcraft.com"));
        assertFalse(AutomationScope.sameServer("",""));
    }
    @Test void reconnectingAtTheLobbyCannotResumeRemoteConstruction(){
        assertFalse(AutomationScope.nearSite(0-761000,0-797840));
        assertTrue(AutomationScope.nearSite(760902-761000,797797-797840));
    }
    @Test void InvalidAndOutOfRangeTargetsFailClosed(){
        assertTrue(AutomationScope.nearSite(512,0));
        assertFalse(AutomationScope.nearSite(512.01,0));
        assertFalse(AutomationScope.nearSite(Double.NaN,0));
        assertFalse(AutomationScope.nearSite(0,Double.POSITIVE_INFINITY));
    }
}
