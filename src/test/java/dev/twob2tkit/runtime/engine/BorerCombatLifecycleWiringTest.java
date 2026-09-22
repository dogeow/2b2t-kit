package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Verify that the real controller cannot bypass the tested combat session during temporary pauses. */
class BorerCombatLifecycleWiringTest {
	private List<String> calls(String type, String name) throws Exception {
		var node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/" + type + ".class")) {
			assertNotNull(in); new ClassReader(in).accept(node, 0);
		}
		var method = node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
		var calls = new ArrayList<String>();
		for (var n : method.instructions) if (n instanceof MethodInsnNode m) calls.add(m.owner.substring(m.owner.lastIndexOf('/') + 1) + "." + m.name);
		return calls;
	}
	@Test void temporaryMiningMenuAndMealPausesCannotEndAnUnfinishedFight() throws Exception {
		for (var method : List.of("tick", "pauseForMeteorFood"))
			assertFalse(calls("DefaultTunnelBorerEngine", method).contains("BorerRangedCombat.end"));
		assertTrue(calls("DefaultTunnelBorerEngine", "tick").contains("BorerRangedCombat.pause"));
		for (var method : List.of("pause", "pauseForEating")) {
			assertTrue(calls("BorerRangedCombat", method).contains("BorerCombatSession.pause"));
			assertFalse(calls("BorerRangedCombat", method).contains("BorerCombatSession.clear"));
		}
	}
	@Test void confirmedDeathRatherThanEntityRemovalFeedsTheCombatSession() throws Exception {
		var calls = calls("BorerRangedCombat", "tick");
		int death = calls.indexOf("LivingEntity.isDeadOrDying");
		assertTrue(death >= 0 && death < calls.indexOf("BorerCombatSession.observe"));
		assertTrue(calls.contains("BorerCombatSession.pending"));
	}
	@Test void actualArrowReleaseRechecksTheWorldAndAttackPermission() throws Exception {
		var calls = calls("BorerRangedCombat", "prepareRelease");
		assertTrue(calls.contains("BorerCombatSession.canAttack"));
		assertTrue(calls.stream().anyMatch(c -> c.endsWith(".getEntity")));
		assertTrue(calls.stream().anyMatch(c -> c.endsWith(".hasLineOfSight")));
	}
	@Test void explicitStopStillReleasesSessionAndControls() throws Exception {
		assertTrue(calls("DefaultTunnelBorerEngine", "stop").contains("BorerRangedCombat.end"));
		var end = calls("BorerRangedCombat", "end");
		assertTrue(end.contains("BorerCombatSession.clear"));
		assertTrue(end.contains("BorerRangedCombat.releaseControls"));
	}
}
