package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GuardRepositionThreatPolicyTest {
    @Test void passiveDistantCasterOrCreeperDoesNotStrandTheEngagedMeleeTarget() {
        assertFalse(GuardRepositionThreatPolicy.blocks(true, true, false, false));
    }
    @Test void incomingArcherAndImminentCreeperStillPreemptTheSideRoute() {
        assertTrue(GuardRepositionThreatPolicy.blocks(true, true, true, false));
    }
    @Test void previouslyEngagedDangerousTargetIsNotForgottenWhenQuiet() {
        assertTrue(GuardRepositionThreatPolicy.blocks(true, true, false, true));
    }
    @Test void deadThreatAndOrdinaryMeleeDoNotReplaceTheExistingPathSafetyChecks() {
        assertFalse(GuardRepositionThreatPolicy.blocks(false, true, true, true));
        assertFalse(GuardRepositionThreatPolicy.blocks(true, false, true, true));
    }
}
