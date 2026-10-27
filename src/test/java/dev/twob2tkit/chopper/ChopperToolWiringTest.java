package dev.twob2tkit.chopper;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ChopperToolWiringTest {
    private ClassNode read(String owner) throws Exception {
        var node = new ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/chopper/" + owner + ".class")) {
            assertNotNull(in);
            new ClassReader(in).accept(node, 0);
        }
        return node;
    }
    private MethodNode method(String owner, String name) throws Exception {
        return read(owner).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(String owner, String name) throws Exception {
        var calls = new ArrayList<String>();
        for (var instruction : method(owner, name).instructions)
            if (instruction instanceof MethodInsnNode call) calls.add(call.name);
        return calls;
    }
    @Test void axeAndShearsUseTheSameDurabilityCheckedSelection() throws Exception {
        assertTrue(calls("AutoChopper", "selectTool").contains("select"));
        assertTrue(calls("ChopperTools", "select").containsAll(List.of("selectToolType", "selectSafeHand")));
        assertTrue(calls("ChopperTools", "selectToolType").containsAll(List.of("chooseSlot", "usableTool", "selectSlot")));
        assertTrue(calls("ChopperTools", "usableTool").contains("tooWorn"));
        assertTrue(calls("ChopperTools", "selectSafeHand").containsAll(List.of("chooseSlot", "selectSlot", "isDamageableItem")));
    }
    @Test void failedSafeSelectionStopsBeforeAnyMiningAction() throws Exception {
        var mine = method("AutoChopper", "mine");
        AbstractInsnNode selected = null;
        for (var instruction : mine.instructions)
            if (instruction instanceof MethodInsnNode call && call.name.equals("selectTool")) selected = instruction;
        assertNotNull(selected);
        assertInstanceOf(JumpInsnNode.class, selected.getNext());
        var branch = (JumpInsnNode) selected.getNext();
        boolean stopped = false, returned = false;
        for (var instruction = branch.getNext(); instruction != branch.label; instruction = instruction.getNext()) {
            assertNotNull(instruction);
            if (instruction instanceof MethodInsnNode call) {
                stopped |= call.name.equals("stop");
                assertFalse(call.name.equals("startDestroyBlock") || call.name.equals("continueDestroyBlock"));
            }
            returned |= instruction.getOpcode() == org.objectweb.asm.Opcodes.IRETURN;
        }
        assertTrue(stopped && returned);
    }

    @Test void platformRemovalChecksTheSameToolsAfterConfirmationAndBeforeAttacking() throws Exception {
        var names = calls("ChopperScaffold", "tick");
        assertTrue(names.indexOf("pending") >= 0 && names.indexOf("require") > names.indexOf("pending"));
        assertTrue(names.indexOf("startDestroyBlock") > names.indexOf("require"));
        assertTrue(names.indexOf("continueDestroyBlock") > names.indexOf("require"));
    }

    @Test void pickupLeafClearingChecksTheSameToolsBeforeExistingAttackInput() throws Exception {
        var names = calls("ChopperLoot", "clearLeafObstacle");
        assertTrue(names.indexOf("require") >= 0 && names.indexOf("clickAttack") > names.indexOf("require"));
        assertTrue(names.indexOf("setDown") > names.indexOf("require"));
        assertTrue(calls("ChopperTools", "require").containsAll(List.of("select", "<init>")));
        assertTrue(java.util.stream.StreamSupport.stream(method("ChopperTools", "require").instructions.spliterator(), false)
            .anyMatch(instruction -> instruction.getOpcode() == org.objectweb.asm.Opcodes.ATHROW));
    }
}
