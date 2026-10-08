package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import java.util.ArrayList;
import static org.junit.jupiter.api.Assertions.*;

class BorerPeekFiringWiringTest {
    private MethodNode method(String owner, String name) throws Exception {
        var node = new ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/" + owner + ".class")) {
            assertNotNull(in);
            new ClassReader(in).accept(node, 0);
        }
        return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    @Test void rangedArrivalRequiresActualHostBallisticsAlongsideLiveGeometry() throws Exception {
        var calls = new ArrayList<String>();
        for (var instruction : method("BorerCombatPeek", "acquired").instructions)
            if (instruction instanceof MethodInsnNode call) calls.add(call.name);
        assertTrue(calls.containsAll(java.util.List.of("hasLineOfSight", "withinAttackRange", "safeDistance", "borerBowAim")));
        assertTrue(calls.indexOf("safeDistance") < calls.indexOf("borerBowAim"));
    }
    @Test void unfinishedPeekContinuesBeforeOrdinaryTargetSelectionCanCloseIt() throws Exception {
        var calls = new ArrayList<String>();
        for (var instruction : method("BorerRangedCombat", "tick").instructions)
            if (instruction instanceof MethodInsnNode call)
                calls.add(call.owner.substring(call.owner.lastIndexOf('/') + 1) + "." + call.name);
        int acquired = calls.indexOf("BorerCombatPeek.acquired");
        int continuation = calls.subList(acquired + 1, calls.size()).indexOf("BorerCombatPeek.tick") + acquired + 1;
        assertTrue(acquired >= 0);
        assertTrue(continuation > acquired && continuation < calls.indexOf("BorerDefensePolicy.choose"));
    }
}
