package dev.twob2tkit.borer;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.JumpInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.*;

class BorerStartSafetyWiringTest {
    @Test
    void menuStartAndHotkeyReturnBeforeTakingOverWhenSafetyLockIsHeld() throws IOException {
        assertBlockedBefore(method("borer/TunnelBorer", "start"), "beforeStart");
        assertBlockedBefore(method("KitClient", "toggleBorer"), "stop");
    }

    @Test
    void miningButtonReportsTheBlockAfterApplyingSettings() throws IOException {
        MethodNode run = method("ClickGuiPages", "lambda$bindMiningRun$", true);
        assertNull(call(run, "prepareForBorer"));
        var start = call(run, "start");
        var reason = call(run, "manualStartBlock");
        assertNotNull(start);
        assertNotNull(reason);
        assertTrue(run.instructions.indexOf(start) < run.instructions.indexOf(reason));
        for (var instruction = reason.getNext(); instruction != null; instruction = instruction.getNext())
            if (instruction instanceof MethodInsnNode call && call.name.equals("showNotice")) return;
        fail("The reason for a rejected start should be shown on the mining page");
    }

    private void assertBlockedBefore(MethodNode entry, String firstSideEffect) {
        var guard = call(entry, "reportManualStartBlocked");
        assertNotNull(guard);
        var branch = assertInstanceOf(JumpInsnNode.class, guard.getNext());
        assertEquals(Opcodes.IFEQ, branch.getOpcode());
        assertEquals(Opcodes.RETURN, branch.getNext().getOpcode());
        assertNotNull(call(entry, firstSideEffect));
        assertTrue(entry.instructions.indexOf(branch.label) < entry.instructions.indexOf(call(entry, firstSideEffect)));
    }

    private MethodNode method(String type, String name) throws IOException {
        return method(type, name, false);
    }

    private MethodNode method(String type, String name, boolean prefix) throws IOException {
        var node = new ClassNode();
        try (var input = getClass().getResourceAsStream("/dev/twob2tkit/" + type + ".class")) {
            assertNotNull(input);
            new ClassReader(input).accept(node, ClassReader.SKIP_DEBUG);
        }
        return node.methods.stream()
            .filter(m -> prefix ? m.name.startsWith(name) && call(m, "start") != null : m.name.equals(name))
            .findFirst().orElseThrow();
    }

    private static MethodInsnNode call(MethodNode method, String name) {
        for (var instruction : method.instructions)
            if (instruction instanceof MethodInsnNode call && call.name.equals(name)) return call;
        return null;
    }

}
