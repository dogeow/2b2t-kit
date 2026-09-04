package dev.twob2tkit;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import dev.twob2tkit.nether.NetherBiomePolicy;

/** 锁住：下界群系采样步长和并片，避免把同一片诡异森林列成几十条。 */
final class NetherBiomePolicyTest {
	@Test
	void quartIsBlockOverFour() {
		assertEquals(16, NetherBiomePolicy.quart(64));
		assertEquals(25, NetherBiomePolicy.quart(100));
	}

	@Test
	void nearbySamplesMergeIntoOnePatch() {
		assertFalse(NetherBiomePolicy.newPatch(32, 0));
		assertFalse(NetherBiomePolicy.newPatch(128, 128));
		assertTrue(NetherBiomePolicy.newPatch(192, 0));
		assertTrue(NetherBiomePolicy.newPatch(200, 50));
	}

	@Test
	void sampleHeightStaysInNetherBand() {
		assertEquals(32, NetherBiomePolicy.sampleY(0));
		assertEquals(64, NetherBiomePolicy.sampleY(64));
		assertEquals(96, NetherBiomePolicy.sampleY(200));
	}
}
