package dev.twob2tkit.chopper;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ChopperMiningWiringTest {
    private ClassNode read() throws Exception {
        var node = new ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/chopper/AutoChopper.class")) {
            assertNotNull(in);
            new ClassReader(in).accept(node, 0);
        }
        return node;
    }
    private MethodNode method(String name) throws Exception {
        return read().methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<MethodInsnNode> calls(MethodNode method) {
        var calls = new ArrayList<MethodInsnNode>();
        for (var instruction : method.instructions)
            if (instruction instanceof MethodInsnNode call) calls.add(call);
        return calls;
    }
    @Test void realMiningUsesVanillaStartAndContinueInsteadOfSyntheticClicksOrHeldAttack() throws Exception {
        var mine = method("mine");
        var calls = calls(mine);
        assertEquals(1, calls.stream().filter(c -> c.name.equals("startDestroyBlock")).count());
        assertEquals(1, calls.stream().filter(c -> c.name.equals("continueDestroyBlock")).count());
        assertFalse(calls.stream().anyMatch(c -> c.name.equals("clickAttack") || c.name.equals("click")));
        int heldWrites = 0;
        for (var call : calls) if (call.name.equals("setDown")) {
            assertEquals(Opcodes.ICONST_0, call.getPrevious().getOpcode());
            heldWrites++;
        }
        assertEquals(1, heldWrites);
    }
    @Test void pendingServerConfirmationReturnsBeforePruningOrMoreMining() throws Exception {
        var tick = method("tick");
        AbstractInsnNode pending = null, prune = null;
        for (var instruction : tick.instructions) if (instruction instanceof MethodInsnNode call) {
            if (call.owner.endsWith("BorerMiningConfirmation") && call.name.equals("pending") && pending == null) pending = instruction;
            if (call.name.equals("pruneGone")) { prune = instruction; break; }
        }
        assertNotNull(pending);
        assertNotNull(prune);
        assertInstanceOf(JumpInsnNode.class, pending.getNext());
        var branch = (JumpInsnNode) pending.getNext();
        boolean heldStill = false, returned = false, timeoutStops = false;
        for (var instruction = branch.getNext(); instruction != branch.label; instruction = instruction.getNext()) {
            assertNotNull(instruction);
            if (instruction instanceof MethodInsnNode call) {
                heldStill |= call.name.equals("holdStill");
                timeoutStops |= call.name.equals("stop");
                assertFalse(List.of("mine", "pruneGone", "startDestroyBlock", "continueDestroyBlock").contains(call.name));
            }
            returned |= instruction.getOpcode() == Opcodes.RETURN;
        }
        assertTrue(heldStill && returned && timeoutStops);
    }
    @Test void predictedLogRemovalCannotCountAsAConfirmedHarvest() throws Exception {
        var predicate = read().methods.stream().filter(m -> m.name.startsWith("lambda$pruneGone$")).findFirst().orElseThrow();
        var names = calls(predicate).stream().map(c -> c.name).toList();
        assertTrue(names.indexOf("pending") >= 0 && names.indexOf("isWood") > names.indexOf("pending"));
        assertTrue(calls(method("verifyCrown")).stream().anyMatch(c -> c.owner.endsWith("BorerMiningConfirmation") && c.name.equals("pending")));
    }
}
