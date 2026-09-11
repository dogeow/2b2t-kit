package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class BorerToolPolicyTest {
	private final BorerToolPolicy tenPercent = new BorerToolPolicy(true, 10, "Blacklist", Set.of());
	@Test void matchesMeteorIntegerFloorAndStrictBoundary() {
		assertFalse(tenPercent.allows("diamond", true, 1561, 155));
		assertTrue(tenPercent.allows("diamond", true, 1561, 156));
		assertTrue(tenPercent.allows("diamond", true, 1561, 157));
	}
	@Test void lastPickProtectedAtTenPercentEvenWhenAboveOldEightPointLimit() {
		assertTrue(BorerToolPolicy.exhausted(List.of(candidate(0, true, 1561, 150, 99))));
	}
	@Test void healthyAxeAndShovelCannotHideExhaustedPickaxes() {
		assertTrue(BorerToolPolicy.exhausted(List.of(candidate(0, true, 1561, 100, 99),
			candidate(3, false, 1561, 1500, 100), candidate(9, false, 1561, 1500, 100))));
	}
	@Test void findsFullInventoryReserveOverProtectedHigherScorePick() {
		var tools = List.of(candidate(0, true, 1561, 100, 9999), candidate(27, true, 1561, 1000, 5));
		assertFalse(BorerToolPolicy.exhausted(tools));
		assertEquals(27, BorerToolPolicy.choose(tools, 0));
	}
	@Test void canUseOffhandReserveAndPrefersAlreadySelectedEqualTool() {
		assertEquals(45, BorerToolPolicy.choose(List.of(candidate(45, true, 1561, 1000, 8)), 0));
		assertEquals(3, BorerToolPolicy.choose(List.of(candidate(0, true, 1561, 1000, 8), candidate(3, true, 1561, 1000, 8)), 3));
	}
	@Test void noSuitableDropToolNeverFallsBackToBestProtectedTool() {
		assertEquals(-1, BorerToolPolicy.choose(List.of(candidate(0, true, 1561, 80, 9999),
			candidate(9, true, 100, 100, -1)), 0));
	}
	@Test void disabledMeteorKeepsLocalEightPointReserveAndAllowsNonDamageableTools() {
		assertTrue(BorerToolPolicy.DEFAULT.allows("pick", true, 1561, 9));
		assertFalse(BorerToolPolicy.DEFAULT.allows("pick", true, 1561, 8));
		assertTrue(tenPercent.allows("unbreakable", false, 1561, 0));
	}
	@Test void followsUserWhitelistAndBlacklistWithoutMutatingThem() {
		var whitelist = new BorerToolPolicy(true, 10, "Whitelist", Set.of("diamond"));
		assertFalse(whitelist.allows("iron", true, 250, 250));
		assertTrue(whitelist.allows("diamond", true, 1561, 1000));
		var blacklist = new BorerToolPolicy(false, 0, "Blacklist", Set.of("diamond"));
		assertFalse(blacklist.allows("diamond", true, 1561, 1561));
	}
	@Test void emptyInventoryDoesNotInventAProtectedPickaxeLogout() {
		assertFalse(BorerToolPolicy.exhausted(List.of()));
		assertFalse(BorerToolPolicy.exhausted(List.of(candidate(0, false, 100, 1, 8))));
	}
	private BorerToolPolicy.Candidate candidate(int slot, boolean pickaxe, int max, int left, float score) {
		return new BorerToolPolicy.Candidate(slot, pickaxe, tenPercent.allows("tool", true, max, left), score);
	}
}
