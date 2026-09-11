package dev.twob2tkit.compat;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ClientWorldGuardTest {
	@Test void missingPlayerWorldOrGameModeMustSkipCombatTicks() {
		Object present = new Object();
		for (int flags = 0; flags < 8; flags++) assertEquals(flags == 7, ClientWorldGuard.ready(
			(flags & 1) != 0 ? present : null, (flags & 2) != 0 ? present : null, (flags & 4) != 0 ? present : null));
	}
	@Test void pendingLogoutOnlyAppliesToItsOriginalSession() {
		Object world = new Object(), connection = new Object();
		assertTrue(ClientWorldGuard.sameSession(world, world, connection, connection));
		assertFalse(ClientWorldGuard.sameSession(world, null, connection, null));
		assertFalse(ClientWorldGuard.sameSession(world, new Object(), connection, connection));
		assertFalse(ClientWorldGuard.sameSession(world, world, connection, new Object()));
		assertFalse(ClientWorldGuard.sameSession(null, null, null, null));
	}
	@Test void damageLogoutThenLateCombatTickSkipsAndReconnectWorksAgain() {
		Object player = new Object(), world = new Object(), gameMode = new Object();
		assertTrue(ClientWorldGuard.ready(player, world, gameMode));
		assertFalse(ClientWorldGuard.ready(null, null, null));
		assertFalse(ClientWorldGuard.ready(player, null, null));
		assertTrue(ClientWorldGuard.ready(new Object(), new Object(), new Object()));
	}
}
