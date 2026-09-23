package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class AutomationFoodPolicyTest {
    @Test void materialOwnerMayEatWhileGuardIsHoldingForHunger() {
        assertTrue(AutomationFoodPolicy.allow(false,true,false,false,false,19.5f,14));
        assertTrue(AutomationFoodPolicy.allow(true,false,false,false,false,19.5f,14));
    }

    @Test void enemyManualControlOrLostScopePreventsForcedEating() {
        assertFalse(AutomationFoodPolicy.allow(false,false,false,false,false,19.5f,14));
        assertFalse(AutomationFoodPolicy.allow(false,true,true,false,false,19.5f,14));
        assertFalse(AutomationFoodPolicy.allow(false,true,false,true,false,19.5f,14));
        assertFalse(AutomationFoodPolicy.allow(false,true,false,false,true,19.5f,14));
        assertFalse(AutomationFoodPolicy.allow(false,true,false,false,false,13.9f,14));
        assertFalse(AutomationFoodPolicy.allow(false,true,false,false,false,19.5f,20));
    }
}
