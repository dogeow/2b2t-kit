package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerHudFrameLimiterTest {
    @Test void samplesBothLinesTogetherWithoutResettingOnEveryCandidate() {
        var limiter = new BorerHudFrameLimiter();
        var first = limiter.update("mining", 0x55FFFF, "target A", 1000);
        assertSame(first, limiter.update("waiting", 0xFFFF55, "target B", 1100));
        assertSame(first, limiter.update("descending", 0x55FFFF, "target C", 1249));
        var next = limiter.update("descending", 0x55FFFF, "target D", 1250);
        assertEquals("descending", next.action());
        assertEquals("target D", next.detail());
        assertEquals(0x55FFFF, next.color());
    }
    @Test void safetyAndCompletionAreImmediate() {
        var limiter = new BorerHudFrameLimiter();
        limiter.update("mining", 0xFFFF55, "", 1000);
        assertEquals("lava", limiter.update("lava", 0xFF5555, "stop", 1001).action());
        assertEquals("health", limiter.update("health", 0xFF5555, "stop", 1002).action());
        assertEquals("complete", limiter.update("complete", 0x55FF55, "done", 1003).action());
    }
    @Test void newSessionAndClockResetCannotReuseAnOldFrame() {
        var limiter = new BorerHudFrameLimiter();
        limiter.update("old", 0x55FFFF, "", 1000);
        limiter.clear();
        assertEquals("new", limiter.update("new", 0xFFFF55, "", 1001).action());
        assertEquals("new world", limiter.update("new world", 0xFFFF55, "", 0).action());
    }
}
