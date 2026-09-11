package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Verify the actual runner selects shallow mode and still owns all break/input and safety gates. */
class BorerAreaHorizontalWiringTest {
    @Test void liveRunnerUsesResolvedBoundsStrategyForBothNewAndRestoredPlans() throws Exception {
        var tick = method("BorerAreaRunner", "tick");
        assertTrue(calls(tick).indexOf("getMinY") < calls(tick).indexOf("enabled"));
        assertTrue(calls(tick).indexOf("enabled") < calls(tick).indexOf("restore"));
        boolean selectedConstructor = false, selectedRestore = false;
        for (AbstractInsnNode i : tick.instructions) if (i instanceof MethodInsnNode call && call.owner.endsWith("/BorerAreaPlan")) {
            if (call.name.equals("<init>")) selectedConstructor |= call.desc.endsWith("Z)V");
            if (call.name.equals("restore")) selectedRestore |= call.desc.contains("Z)");
        }
        assertTrue(selectedConstructor); assertTrue(selectedRestore);
        assertTrue(calls(method("BorerAreaRunner", "canResumeHere")).contains("enabled"));
    }
    @Test void horizontalFeasibilityUsesRealVisibilityAndMineStillChecksActualViewAndReach() throws Exception {
        assertTrue(calls(method("BorerAreaRunner$1", "canMine")).contains("visibleHit"));
        var mine = calls(method("BorerAreaRunner", "mine"));
        assertTrue(mine.contains("clipView")); assertTrue(mine.contains("breakReach"));
        assertTrue(mine.indexOf("clipView") < mine.indexOf("setDown"));
        assertTrue(calls(method("BorerAreaPlan", "horizontalStep")).contains("canMine"));
        // Horizontal clearing never issues a simultaneous forward-attack input or an automatic jump.
        for (AbstractInsnNode i : method("BorerAreaPlan", "horizontalStep").instructions)
            if (i instanceof FieldInsnNode f && f.getOpcode() == Opcodes.GETSTATIC) assertNotEquals("MINE_DOWN", f.name);
    }
    @Test void safetyOwnersStillRunBeforeHorizontalPlannerAndCellArrivalStillTriggersLighting() throws Exception {
        var tick = calls(method("BorerAreaRunner", "tick"));
        assertTrue(tick.indexOf("isInWater") < tick.indexOf("step"));
        assertTrue(tick.indexOf("shouldStart") < tick.indexOf("step"));
        assertTrue(tick.contains("reserveStorageColumn")); assertTrue(tick.contains("resumeAfterStorage"));
        assertTrue(tick.indexOf("reachedBottomThisStep") < tick.lastIndexOf("begin"));
        assertTrue(calls(method("BorerAreaRunner", "rescue")).contains("skipLiquid"));
    }
    private static ClassNode node(String type) throws Exception {
        var node = new ClassNode();
        try (var in = BorerAreaHorizontalWiringTest.class.getResourceAsStream("/dev/twob2tkit/runtime/engine/" + type + ".class")) {
            assertNotNull(in); new ClassReader(in).accept(node, 0);
        }
        return node;
    }
    private static MethodNode method(String type, String name) throws Exception { return node(type).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow(); }
    private static List<String> calls(MethodNode method) { List<String> calls = new ArrayList<>(); for (AbstractInsnNode i : method.instructions) if (i instanceof MethodInsnNode m) calls.add(m.name); return calls; }
}
