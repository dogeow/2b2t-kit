package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** A block that keeps coming back after a confirmed break is logged and eventually left alone; placements are logged. */
class BorerReappearWiringTest {
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
	void settingATargetChecksForBlocksThatReappearedAfterAConfirmedBreak() throws Exception {
		List<String> calls = calls(method("DefaultTunnelBorerEngine", "setMiningTarget"));
		assertTrue(calls.contains("dev/twob2tkit/runtime/engine/BorerReappearance.observe"));
		assertTrue(calls.contains("dev/twob2tkit/runtime/engine/BorerMiningPolicy.suppressReappearedBlock"));
	}

	@Test
	void everyPlacedSupportIsLogged() throws Exception {
		assertTrue(calls(method("BorerPlace", "rememberPlacedSupport"))
			.contains("dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.fileLog"));
	}
}
