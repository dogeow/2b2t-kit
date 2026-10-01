package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** Lava contact must stop and back away on ground, never enable Meteor flight thrash. */
class BorerLavaRetreatWiringTest {
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
	void lavaContactNeverEnablesMeteorFlightAndPrefersGroundRetreat() throws Exception {
		var c = calls(method("BorerLiquids", "handleLavaContact"));
		assertFalse(c.stream().anyMatch(x -> x.endsWith(".enableMeteorFlight")),
			"Lava contact must not enable Meteor flight");
		assertTrue(c.stream().anyMatch(x -> x.endsWith(".releaseMine")),
			"Lava contact must stop digging");
		assertTrue(c.stream().anyMatch(x -> x.endsWith(".tryStepOffMagma") || x.endsWith(".preferGroundRetreatFromLava")),
			"Lava contact must attempt ground retreat");
		assertTrue(c.stream().anyMatch(x -> x.endsWith(".stopInsteadOfFlightThrash") || x.endsWith(".stop")),
			"When ground retreat fails, stop rather than thrash");
	}

	@Test
	void hazardRefuseRunsBeforeServerClearedPath() throws Exception {
		var c = calls(method("DefaultTunnelBorerEngine", "tick"));
		int refuse = index(c, ".refuseOpenedHazard");
		int cleared = index(c, ".treatAsServerCleared");
		assertTrue(refuse >= 0, "tick must refuse opened lava/water explicitly");
		assertTrue(cleared >= 0, "tick must gate server-cleared on block-gone");
		assertTrue(refuse < cleared, "hazard refuse must precede cleared handling");
	}

	private static int index(List<String> calls, String suffix) {
		for (int i = 0; i < calls.size(); i++) if (calls.get(i).endsWith(suffix)) return i;
		return -1;
	}
}
