package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** Magma mining walks onto lava-free magma instead of reporting the floor ahead as unsafe. */
class BorerMagmaWalkWiringTest {
	private MethodNode method(String type, String name) throws Exception {
		var node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/" + type + ".class")) {
			assertNotNull(in);
			new ClassReader(in).accept(node, 0);
		}
		return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
	}

	private List<String> calls(MethodNode method) {
		var result = new ArrayList<String>();
		for (var i : method.instructions) {
			if (i instanceof MethodInsnNode call) result.add(call.owner + "." + call.name);
		}
		return result;
	}

	@Test
	void safeMagmaFloorIsCheckedBeforeTheFallDepthScan() throws Exception {
		// 2026-11-03: "目标路线前方地板连续 4 秒不安全" on an all-magma, lava-free floor.
		List<String> calls = calls(method("DefaultTunnelBorerEngine", "unsafeToWalk"));
		int magma = calls.indexOf("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.dropOntoSafeMagma");
		int fall = calls.indexOf("dev/twob2tkit/runtime/engine/BorerHazards.safeFallDepth");
		assertTrue(magma >= 0, "unsafeToWalk must consult dropOntoSafeMagma");
		assertTrue(fall > magma, "safe magma must short-circuit before the fall-depth scan");
		assertTrue(calls(method("DefaultTunnelBorerEngine", "dropOntoSafeMagma"))
			.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.safeMagmaFloor"));
	}

	@Test
	void flightBypassesGroundCrouchCheckOnlyAfterFluidChecks() throws Exception {
		List<String> calls = calls(method("DefaultTunnelBorerEngine", "unsafeToWalk"));
		String engine = "dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.";
		int flight = calls.indexOf(engine + "isFlying");
		assertTrue(calls.lastIndexOf(engine + "isLava") >= 0);
		assertTrue(calls.lastIndexOf(engine + "isLava") < flight);
		assertTrue(calls.lastIndexOf("dev/twob2tkit/runtime/engine/BorerHazards.isWater") < flight);
		assertTrue(flight < calls.indexOf(engine + "sneakOnMagma"));
	}

	@Test
	void detourChecksTheSameMagmaFloorSafetyAsMovement() throws Exception {
		assertTrue(calls(method("BorerLiquids", "inStandColumn"))
			.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.safeMagmaFloor"));
	}

	@Test
	void walkwayPavingSkipsDropsOntoSafeMagma() throws Exception {
		// 2026-11-03: support placed above magma, then mined, repeatedly.
		assertTrue(calls(method("BorerPlace", "shouldBridgeDrops"))
			.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.dropOntoSafeMagma"));
	}

	@Test
	void standabilityAndLootRoutesAcceptSafeMagma() throws Exception {
		assertTrue(calls(method("DefaultTunnelBorerEngine", "isStandable"))
			.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.safeMagmaFloor"));
		assertTrue(calls(method("DefaultTunnelBorerEngine", "safeMagmaFloor"))
			.contains("dev/twob2tkit/runtime/engine/BorerLiquidPolicy.safeMagmaFloor"));
	}

	@Test
	void anyNonAreaMiningCrouchesAcrossSafeMagmaNotOnlyMagmaTargets() throws Exception {
		// 2026-11-03: magma on the way to other ores should be crossed crouched, not avoided.
		for (String name : new String[]{"safeMagmaFloor", "sneakOnMagma"}) {
			List<String> calls = calls(method("DefaultTunnelBorerEngine", name));
			assertTrue(calls.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.magmaWalk"), name);
			assertFalse(calls.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.magmaMining"), name);
		}
	}
}
