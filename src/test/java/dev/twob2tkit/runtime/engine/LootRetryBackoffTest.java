package dev.twob2tkit.runtime.engine;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LootRetryBackoffTest {
    @Test void twoUnreachableDropsCannotPingPongAfterEachEightSecondAttempt() {
        LootRetryBackoff retry = new LootRetryBackoff();
        UUID first=UUID.randomUUID(), second=UUID.randomUUID();
        long firstUntil=retry.nextDelay(first);
        long secondUntil=160+retry.nextDelay(second);
        assertTrue(firstUntil>320 && secondUntil>320);
        assertEquals(1200,retry.nextDelay(first));
        assertEquals(1800,retry.nextDelay(first));
        assertEquals(1800,retry.nextDelay(first));
        retry.clear();
        assertEquals(600,retry.nextDelay(first));
    }
    @Test void unobservedIdentityIsNotAccepted() {
        assertThrows(IllegalArgumentException.class,()->new LootRetryBackoff().nextDelay(null));
    }
}
