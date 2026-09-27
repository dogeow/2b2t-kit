package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

class BorerCombatContinuationWiringTest {
	private MethodNode method(String name) throws Exception {
		var node = new ClassNode();
		try (var input = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/BorerRangedCombat.class")) {
			assertNotNull(input);
			new ClassReader(input).accept(node, 0);
		}
		return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
	}

	/** Follow the real tick branches with only the restored-missing flag fixed.
	 * All other conditions may take either branch; no Minecraft client is started. */
	private Set<String> reachableCalls(boolean missing) throws Exception {
		var tick = method("tick");
		MethodInsnNode restore = null;
		for (var instruction : tick.instructions) {
			if (instruction instanceof MethodInsnNode call && call.name.equals("restore")
				&& call.owner.endsWith("/BorerCombatContinuation")) restore = call;
		}
		assertNotNull(restore);
		var stored = restore.getNext();
		while (stored.getOpcode() < 0) stored = stored.getNext();
		assertInstanceOf(VarInsnNode.class, stored);
		assertEquals(Opcodes.ISTORE, stored.getOpcode());
		int missingSlot = ((VarInsnNode) stored).var;
		var queue = new ArrayDeque<AbstractInsnNode>();
		var visited = new HashSet<AbstractInsnNode>();
		var calls = new HashSet<String>();
		queue.add(stored.getNext());
		while (!queue.isEmpty()) {
			var instruction = queue.removeFirst();
			if (!visited.add(instruction)) continue;
			if (instruction instanceof MethodInsnNode call) calls.add(call.name);
			int opcode = instruction.getOpcode();
			if (opcode >= Opcodes.IRETURN && opcode <= Opcodes.RETURN || opcode == Opcodes.ATHROW) continue;
			if (instruction instanceof JumpInsnNode branch) {
				if (opcode == Opcodes.GOTO) { queue.add(branch.label); continue; }
				var value = instruction.getPrevious();
				while (value != null && value.getOpcode() < 0) value = value.getPrevious();
				if (value instanceof VarInsnNode load && load.getOpcode() == Opcodes.ILOAD
					&& load.var == missingSlot) {
					assertTrue(opcode == Opcodes.IFEQ || opcode == Opcodes.IFNE);
					boolean jump = opcode == Opcodes.IFNE ? missing : !missing;
					queue.add(jump ? branch.label : instruction.getNext());
					continue;
				}
				queue.add(branch.label);
			}
			if (instruction.getNext() != null) queue.add(instruction.getNext());
		}
		return calls;
	}

	@Test void missingOldThreatCannotSuppressCurrentDefenseOrResumeWork() throws Exception {
		var calls = reachableCalls(true);
		assertTrue(calls.containsAll(Set.of("evadeCreeper", "attack", "selectBow", "holdForMissingObservation")),
			"An unobserved old UUID must still allow current creeper evasion, melee, and bow defense");
		assertFalse(calls.contains("end"), "Neither current kills nor relocation can clear an unobserved old target");
	}

	@Test void confirmedFinishCanResumeWhenNoRestoredThreatIsMissing() throws Exception {
		var calls = reachableCalls(false);
		assertTrue(calls.contains("end"));
		assertFalse(calls.contains("holdForMissingObservation"));
	}

	@Test void missingObservationHoldReleasesControlsButPreservesUnresolvedTargets() throws Exception {
		var calls = new HashSet<String>();
		for (var instruction : method("holdForMissingObservation").instructions) {
			if (instruction instanceof MethodInsnNode call) calls.add(call.name);
		}
		assertTrue(calls.containsAll(Set.of("releaseControls", "raiseShield")));
		assertFalse(calls.contains("clear"));
		assertFalse(calls.contains("end"));
	}
}
