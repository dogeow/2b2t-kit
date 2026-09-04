package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.borer.BorerHotReloadPolicy;

final class BorerHotReloadPolicyTest {
	@Test
	void waitsUntilNewJarStopsChanging() {
		assertFalse(BorerHotReloadPolicy.jarNewer(100, 100));
		assertTrue(BorerHotReloadPolicy.jarNewer(100, 200));
		assertFalse(BorerHotReloadPolicy.stable(10, BorerHotReloadPolicy.STABLE_TICKS));
		assertTrue(BorerHotReloadPolicy.stable(40, BorerHotReloadPolicy.STABLE_TICKS));
	}
}
