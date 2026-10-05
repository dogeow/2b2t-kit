package dev.twob2tkit.compat;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MeteorFlightWorldGuardTest {
	@Test void missingPlayerSkipsOnlyTheOptionalAbilitiesConditionWithoutDereferencingIt() {
		assertTrue(ClientWorldGuard.spectatorOrMissingPlayer(null, () -> {
			throw new AssertionError("No cleared player may be queried");
		}));
		assertTrue(ClientWorldGuard.spectatorOrMissingPlayer(null, null));
	}
	@Test void existingSpectatorOrSurvivalPlayerKeepsTheOriginalConditionAndSingleQuery() {
		for (boolean actual : new boolean[]{false, true}) {
			var calls = new AtomicInteger();
			assertEquals(actual, ClientWorldGuard.spectatorOrMissingPlayer(new Object(), () -> {
				calls.incrementAndGet(); return actual;
			}));
			assertEquals(1, calls.get());
		}
	}
	@Test void existingPlayerCleanupDoesNotRequireAStillLoadedWorldOrHideOtherFailures() {
		Object player = new Object();
		assertFalse(ClientWorldGuard.ready(player, null, null));
		assertFalse(ClientWorldGuard.spectatorOrMissingPlayer(player, () -> false));
		var original = new IllegalStateException("Unrelated actual query failure");
		assertSame(original, assertThrows(IllegalStateException.class,
			() -> ClientWorldGuard.spectatorOrMissingPlayer(player, () -> { throw original; })));
	}
}
