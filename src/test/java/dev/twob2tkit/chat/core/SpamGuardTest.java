package dev.twob2tkit.chat.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SpamGuardTest {
    @Test
    void tracksInterleavedSendersAndReportsEachBlockOnlyOnce() {
        SpamGuard guard = new SpamGuard(3, 15_000);
        assertEquals(new SpamGuard.Decision(false, false), guard.inspect("uuid-a", "hello", 0));
        assertFalse(guard.inspect("uuid-b", "hello", 1).suppress());
        assertEquals(new SpamGuard.Decision(true, false), guard.inspect("uuid-a", "hello", 2));
        assertEquals(new SpamGuard.Decision(true, true), guard.inspect("uuid-a", "hello", 3));
        assertEquals(new SpamGuard.Decision(true, false), guard.inspect("uuid-a", "different", 99_000));
        assertFalse(guard.blocked("uuid-b"));
        assertEquals(1, guard.blockedPlayers().size());
    }

    @Test
    void formattingCaseWhitespaceCompatibilityAndZeroWidthDoNotEvadeRepetition() {
        SpamGuard guard = new SpamGuard(3, 15_000);
        assertFalse(guard.inspect("player", "Hello world", 1).suppress());
        assertTrue(guard.inspect("player", "§aＨＥＬＬＯ\t\nworld§r", 2).suppress());
        assertTrue(guard.inspect("player", "  He\u200bllo\u00a0WORLD  ", 3).newlyBlocked());
        assertEquals("hello world", SpamGuard.normalize("§aＨＥＬＬＯ\t world§r"));
    }

    @Test
    void fixedWindowExpiresAtTheBoundaryAndDifferentTextResetsTheRun() {
        SpamGuard guard = new SpamGuard(3, 15_000);
        guard.inspect("player", "hello", 0);
        assertTrue(guard.inspect("player", "hello", 14_999).suppress());
        assertFalse(guard.inspect("player", "hello", 15_000).suppress());
        assertFalse(guard.inspect("player", "different", 15_001).suppress());
        assertFalse(guard.inspect("player", "hello", 15_002).suppress());
        assertTrue(guard.inspect("player", "hello", 15_003).suppress());
        assertFalse(guard.blocked("player"));
        assertFalse(guard.inspect("player", "hello", 10).suppress(), "Clock rollback starts a fresh window");
    }

    @Test
    void unblockAndSessionResetStartFreshCounters() {
        SpamGuard guard = new SpamGuard(2, 15_000);
        guard.inspect("one", "hello", 0);
        assertTrue(guard.inspect("one", "hello", 1).newlyBlocked());
        var snapshot = guard.blockedPlayers();
        assertTrue(guard.unblock("one"));
        assertTrue(snapshot.contains("one"), "Returned snapshots must not change later");
        assertFalse(guard.inspect("one", "hello", 2).suppress());
        assertTrue(guard.inspect("one", "hello", 3).newlyBlocked());
        guard.inspect("two", "hello", 3);
        guard.clear();
        assertTrue(guard.blockedPlayers().isEmpty());
        assertFalse(guard.inspect("one", "hello", 4).suppress());
        assertFalse(guard.inspect("two", "hello", 4).suppress());
        assertTrue(guard.block("restored"));
        assertFalse(guard.block("restored"));
        assertEquals(new SpamGuard.Decision(true, false), guard.inspect("restored", "new text", 5));
    }

    @Test
    void fullBlockListDoesNotForgetBlockedPlayersOrEmitRepeatedBlockEvents() {
        SpamGuard guard = new SpamGuard(2, 15_000);
        for (int i = 0; i < 1024; i++) {
            guard.inspect("sender-" + i, "spam", 0);
            assertTrue(guard.inspect("sender-" + i, "spam", 1).newlyBlocked());
        }
        guard.inspect("overflow", "spam", 2);
        assertEquals(new SpamGuard.Decision(true, false), guard.inspect("overflow", "spam", 3));
        assertTrue(guard.blocked("sender-0"));
        assertEquals(1024, guard.blockedPlayers().size());
        for (int i = 0; i < 1100; i++) {
            guard.inspect("new-" + i, "hello", 4);
        }
        assertTrue(guard.blocked("sender-0"));
        assertFalse(guard.inspect("new-0", "hello", 5).suppress(), "Old unblocked sender counters may be evicted");
    }
}
