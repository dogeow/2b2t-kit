package dev.twob2tkit.borer;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

/** Verify the real screen lifecycle uses persistence, not just a standalone draft serializer. */
class AreaDraftWiringTest {
    @Test void everyScreenRemovalPersistsBeforeTheBaseHook() throws Exception {
        var removed = method("AreaSetupScreen", "removed");
        int remember = call(removed, "rememberDraft");
        assertTrue(remember >= 0 && remember < call(removed, "removed"));
        assertEquals(Opcodes.ICONST_1, removed.instructions.get(remember).getPrevious().getOpcode());
    }
    @Test void pointButtonsPersistDraftsWithoutApplyingOrStartingMining() throws Exception {
        var point = method("AreaSetupScreen", "setPoint");
        assertTrue(call(point, "setValue") < call(point, "rememberDraft"));
        assertTrue(call(point, "rememberDraft") >= 0);
        assertEquals(-1, call(point, "apply")); assertEquals(-1, call(point, "start"));
        assertEquals(-1, call(point, "setA")); assertEquals(-1, call(point, "setB"));
    }
    @Test void partialSaveHasAReturnBeforeFullApplyAndNoMiningStart() throws Exception {
        var save = method("AreaSetupScreen", "saveProject");
        int validate = call(save, "parseDraft"), apply = call(save, "apply");
        assertTrue(validate >= 0 && apply > validate);
        boolean returns = false, persists = false;
        for (int i = validate; i < apply; i++) {
            if (save.instructions.get(i).getOpcode() == Opcodes.RETURN) returns = true;
            if (save.instructions.get(i) instanceof MethodInsnNode m && m.name.equals("rememberDraft")) persists = true;
        }
        assertTrue(returns && persists); assertEquals(-1, call(save, "start"));
        assertTrue(call(save, "upsertAreaProject") > apply);
        assertTrue(call(method("AreaSetupScreen", "apply"), "parse") >= 0);
    }
    @Test void rebuildUsesPersistedDraftAndManagerGuardsAgainstSavingStaleBounds() throws Exception {
        var init = method("AreaSetupScreen", "init");
        assertTrue(call(init, "rememberDraft") < call(init, "open"));
        assertTrue(call(init, "open") < call(init, "field"));
        var save = method("AreaProjectsScreen", "saveProject");
        assertTrue(call(save, "hasUnappliedCorners") >= 0 && call(save, "hasUnappliedCorners") < call(save, "upsertAreaProject"));
    }
    private static MethodNode method(String type, String name) throws Exception {
        var node = new ClassNode();
        try (var input = AreaDraftWiringTest.class.getResourceAsStream("/dev/twob2tkit/borer/" + type + ".class")) {
            assertNotNull(input); new ClassReader(input).accept(node, 0);
        }
        return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private static int call(MethodNode method, String name) {
        for (int i = 0; i < method.instructions.size(); i++)
            if (method.instructions.get(i) instanceof MethodInsnNode call && call.name.equals(name)) return i;
        return -1;
    }
}
