package dev.twob2tkit;

import dev.twob2tkit.fisher.FisherCatchPolicy;
import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

final class FisherCatchPolicyTest {
    @Test
    void oneFishCannotBecomeThreeWhileOldHookWaitsForServerRemoval() {
        var policy = new FisherCatchPolicy();
        UUID hook = UUID.randomUUID();
        assertTrue(policy.recordUse(hook, 0, true, true, false));
        for (int cooldown : new int[]{12, 11, 1, 0, 0, 0}) {
            assertFalse(policy.mayUse(hook, cooldown));
            assertFalse(policy.recordUse(hook, cooldown, true, true, false));
        }
        assertEquals(1, policy.catches());
    }

    @Test
    void cooldownAndRejectedUsesDoNotCountOrConsumeHook() {
        var policy = new FisherCatchPolicy();
        UUID hook = UUID.randomUUID();
        assertFalse(policy.recordUse(hook, 2, true, true, false));
        assertFalse(policy.recordUse(hook, 0, false, true, false));
        assertEquals(0, policy.catches());
        assertTrue(policy.mayUse(hook, 0));
        assertTrue(policy.recordUse(hook, 0, true, true, false));
        assertEquals(1, policy.catches());
    }

    @Test
    void CastsEmptyRetrievalsAndHookedEntitiesAreNotFish() {
        var policy = new FisherCatchPolicy();
        assertTrue(policy.recordUse(null, 0, true, false, false));
        assertTrue(policy.recordUse(UUID.randomUUID(), 0, true, false, false));
        UUID entityHook = UUID.randomUUID();
        assertTrue(policy.recordUse(entityHook, 0, true, true, true));
        assertFalse(policy.mayUse(entityHook, 0));
        assertEquals(0, policy.catches());
    }

    @Test
    void distinctFishAndNewSessionsHaveIndependentCounts() {
        var policy = new FisherCatchPolicy();
        UUID first = UUID.randomUUID(), second = UUID.randomUUID();
        policy.recordUse(first, 0, true, true, false);
        assertTrue(policy.mayUse(null, 0));
        assertFalse(policy.mayUse(first, 0));
        policy.recordUse(second, 0, true, true, false);
        assertEquals(2, policy.catches());
        policy.reset();
        assertEquals(0, policy.catches());
        assertTrue(policy.mayUse(second, 0));
    }
}
