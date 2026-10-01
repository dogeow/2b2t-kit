package dev.twob2tkit.structure;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class SeedHintPolicyTest {
	@Test void storedFullSeedRemainsAHintWhenCurrentLoginHashChanges() {
		assertTrue(SeedHintPolicy.available(123L,true,false));
		assertTrue(SeedHintPolicy.available(123L,false,false));
		assertTrue(SeedHintPolicy.available(123L,true,true));
	}

	@Test void noStoredFullSeedDisablesTheLocatorAndAllowsCoarseFallback() {
		assertFalse(SeedHintPolicy.available(null,true,true));
		assertFalse(SeedHintPolicy.available(null,false,false));
	}
}
