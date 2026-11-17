package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class BorerFallingEscapeWiringTest {
    @Test void supportedStackReplansAndRealFallUsesDryHorizontalEscape() throws Exception {
        var node = new ClassNode();
        try (var bytes = getClass().getResourceAsStream("DefaultTunnelBorerEngine.class")) {
            assertNotNull(bytes);
            new ClassReader(bytes).accept(node, 0);
        }
        var handle = node.methods.stream().filter(m -> m.name.equals("handleFallingSand")).findFirst().orElseThrow();
        var checks = new ArrayList<String>();
        for (var instruction : handle.instructions) {
            if (instruction instanceof MethodInsnNode call) checks.add(call.name);
        }
        assertTrue(checks.containsAll(List.of("unsupportedFallingAbove", "wouldCrushPlayer",
            "pending", "suppressMiningTarget", "clearMiningTarget")));

        var dodge = node.methods.stream().filter(m -> m.name.equals("dodgeFallingSand")).findFirst().orElseThrow();
        var calls = new ArrayList<String>();
        for (var instruction : dodge.instructions) {
            if (instruction instanceof MethodInsnNode call) calls.add(call.name);
            if (instruction instanceof FieldInsnNode field) assertNotEquals("keyJump", field.name);
        }
        assertTrue(calls.containsAll(List.of("releaseMine", "stop", "noCollision", "fallingEscapeDry", "enableMeteorFlight")));
        assertTrue(calls.indexOf("fallingEscapeDry") < calls.indexOf("enableMeteorFlight"));
    }
}
