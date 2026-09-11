package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

/** Structural UI checks without launching a client or touching the user's saved places. */
class SavedPlacesWiringTest {
	@Test void editorStartsCollapsedAndOnlyCollapsesAfterSuccessfulSave() throws Exception {
		for (AbstractInsnNode insn : method("<init>").instructions) {
			if (insn instanceof FieldInsnNode field && field.name.equals("editorOpen") && field.getOpcode() == Opcodes.PUTFIELD)
				assertEquals(Opcodes.ICONST_0, previousCode(insn).getOpcode());
		}
		var save = method("savePlace");
		int update = callIndex(save, "upsertPlace"), collapse = fieldIndex(save, "editorOpen");
		assertTrue(update >= 0 && collapse > update);
		assertEquals(Opcodes.ICONST_0, previousCode(save.instructions.get(collapse)).getOpcode());
		assertTrue(callIndex(save, "rebuildWidgets") > collapse);
	}
	@Test void rebuildCapturesDraftsAndScrollBeforeReplacingControls() throws Exception {
		var init = method("init");
		for (String draft : List.of("draftName", "draftX", "draftZ", "draftY")) {
			assertTrue(fieldIndex(init, draft) >= 0);
			assertTrue(fieldIndex(init, draft) < fieldIndex(init, "placeName"));
		}
		assertTrue(callIndex(init, "scrollAmount") >= 0);
		assertTrue(callIndex(init, "scrollAmount") < callIndex(init, "setScrollAmount"));
		assertTrue(callIndex(init, "getValue") < callIndex(init, "buildEditor"));
	}
	@Test void rowEditLoadsDraftsThenOpensEditorWithoutStartingTravel() throws Exception {
		var edit = method("loadPlace");
		int open = fieldIndex(edit, "editorOpen");
		assertTrue(open >= 0); assertEquals(Opcodes.ICONST_1, previousCode(edit.instructions.get(open)).getOpcode());
		for (String draft : List.of("draftName", "draftX", "draftZ", "draftY"))
			assertTrue(fieldIndex(edit, draft) >= 0 && fieldIndex(edit, draft) < open);
		assertTrue(fieldIndex(edit, "placeName") < callIndex(edit, "rebuildWidgets"));
		assertEquals(-1, callIndex(edit, "start")); assertEquals(-1, callIndex(edit, "travel"));
	}
	private static MethodNode method(String name) throws Exception {
		var node = new ClassNode();
		try (var input = SavedPlacesWiringTest.class.getResourceAsStream("/dev/twob2tkit/KitSavedPlacesScreen.class")) {
			assertNotNull(input); new ClassReader(input).accept(node, 0);
		}
		return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
	}
	private static AbstractInsnNode previousCode(AbstractInsnNode insn) {
		do { insn = insn.getPrevious(); } while (insn != null && insn.getOpcode() < 0);
		assertNotNull(insn); return insn;
	}
	private static int fieldIndex(MethodNode method, String name) {
		for (int i = 0; i < method.instructions.size(); i++)
			if (method.instructions.get(i) instanceof FieldInsnNode field && field.name.equals(name) && field.getOpcode() == Opcodes.PUTFIELD) return i;
		return -1;
	}
	private static int callIndex(MethodNode method, String name) {
		for (int i = 0; i < method.instructions.size(); i++)
			if (method.instructions.get(i) instanceof MethodInsnNode call && call.name.equals(name)) return i;
		return -1;
	}
}
