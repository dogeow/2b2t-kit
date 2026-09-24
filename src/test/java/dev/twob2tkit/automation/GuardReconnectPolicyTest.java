package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class GuardReconnectPolicyTest {
	@Test void unexpectedReconnectCanRestoreOnlyTheSamePveSite() {
		var pending = GuardReconnectPolicy.capture(true, true, true, 20,
			"simpcraft.com:25565", "minecraft:overworld", 760939, 797936, 1000);
		assertNotNull(pending);
		assertTrue(GuardReconnectPolicy.restoreHere(pending, "simpcraft.com:25565",
			"minecraft:overworld", 760940, 797938, 20, false, false, 2000));
		assertFalse(GuardReconnectPolicy.restoreHere(pending, "simpcraft.com:25565",
			"minecraft:overworld", 100, 100, 20, false, false, 2000));
		assertFalse(GuardReconnectPolicy.restoreHere(pending, "simpcraft.com:25565",
			"minecraft:the_nether", 760939, 797936, 20, false, false, 2000));
		assertFalse(GuardReconnectPolicy.restoreHere(pending, "simpcraft.com:25565",
			"minecraft:overworld", 760939, 797936, 17, false, false, 2000));
	}

	@Test void manualStopLowHealthAndExpiredConnectionNeverRestoreGuard() {
		assertNull(GuardReconnectPolicy.capture(false, true, true, 20, "s", "d", 1, 2, 1000));
		assertNull(GuardReconnectPolicy.capture(true, true, false, 20, "s", "d", 1, 2, 1000));
		assertNull(GuardReconnectPolicy.capture(true, true, true, 13, "s", "d", 1, 2, 1000));
		var pending = GuardReconnectPolicy.capture(true, true, true, 20, "s", "d", 1, 2, 1000);
		assertFalse(GuardReconnectPolicy.restoreHere(pending, "s", "d", 1, 2, 20, true, false, 2000));
		assertFalse(GuardReconnectPolicy.restoreHere(pending, "s", "d", 1, 2, 20, false, true, 2000));
		assertFalse(GuardReconnectPolicy.restoreHere(pending, "s", "d", 1, 2, 20, false, false,
			1000 + GuardReconnectPolicy.MAX_AGE_MS + 1));
	}
}
