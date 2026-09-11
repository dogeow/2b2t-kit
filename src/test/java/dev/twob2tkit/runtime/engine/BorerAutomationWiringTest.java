package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

/** Check real controller wiring as well as pure policies, without launching a game/world. */
class BorerAutomationWiringTest {
	@Test void foodGuardAndProtectionRunBeforeAreaDispatchAndGenericToolSelection() throws Exception {
		var tick = method("DefaultTunnelBorerEngine", "tick");
		assertTrue(index(tick, "pauseForMeteorFood") < index(tick, "logoutIfToolsWorn"));
		assertTrue(index(tick, "logoutIfToolsWorn") < index(tick, "tickArea"));
		assertTrue(index(tick, "pauseForMeteorFood") < index(tick, "selectMiningTool"));
		assertTrue(calls(method("DefaultTunnelBorerEngine", "reapplyLook")).contains("paused"));
	}
	@Test void areaMealPauseDoesNotReleaseUseChangeHotbarOrDiscardPlan() throws Exception {
		var pause = method("BorerAreaRunner", "suspendForEating");
		assertFalse(fields(pause).contains("keyUse"));
		assertFalse(calls(pause).contains("setSelectedSlot"));
		assertFalse(calls(pause).contains("reset"));
		assertFalse(calls(pause).contains("releaseMovement"));
		assertTrue(calls(pause).containsAll(List.of("pause", "checkpoint", "stopAttack", "hover")));
		assertFalse(fields(method("DefaultTunnelBorerEngine", "releaseMine")).contains("keyUse"));
	}
	@Test void mealPauseKeepsRangedModuleLeaseAndFoodSlotUntilAfterEating() throws Exception {
		var calls = calls(method("BorerRangedCombat", "pauseForEating"));
		assertFalse(calls.contains("rangedMode")); assertFalse(calls.contains("setSelectedSlot"));
		assertFalse(calls.contains("cancelDraw"));
		assertTrue(calls.contains("stopUsingItem")); // Only the BOW-gated path, not the food use.
		assertTrue(fields(method("BorerRangedCombat", "pauseForEating")).contains("BOW"));
	}
	@Test void exhaustedToolsStopAndQueueLogoutWithoutReturnHome() throws Exception {
		var method = method("DefaultTunnelBorerEngine", "logoutIfToolsWorn");
		assertTrue(index(method, "stop") < index(method, "disconnectFromServer"));
		assertFalse(calls(method).contains("finishSession"));
		assertTrue(calls(method("DefaultTunnelBorerEngine", "disconnectFromServer")).contains("schedule"));
		assertFalse(calls(method("DefaultTunnelBorerEngine", "disconnectFromServer")).contains("execute"));
	}
	@Test void everyMiningToolSelectionConsumesSuccessAndCannotFallThroughAfterFailedSwap() throws Exception {
		int sites = 0;
		for (String type : List.of("DefaultTunnelBorerEngine", "BorerAreaRunner", "BorerPlace")) {
			for (MethodNode method : node(type).methods) for (AbstractInsnNode insn : method.instructions) {
				if (insn instanceof MethodInsnNode call && call.name.equals("selectMiningTool")) {
					assertTrue(call.desc.endsWith(")Z"));
					AbstractInsnNode next = call.getNext();
					while (next != null && next.getOpcode() < 0) next = next.getNext();
					assertInstanceOf(JumpInsnNode.class, next, type + "." + method.name);
					sites++;
				}
			}
		}
		assertEquals(3, sites);
	}
	@Test void cargoUsesAllLoadedBlockEntitiesAndChecksExistingStorageBeforePlacement() throws Exception {
		var choose = method("BorerAreaCargo", "chooseDepot");
		assertTrue(index(choose, "getBlockEntities") < index(choose, "columns"));
		assertTrue(index(choose, "acceptsAny") < index(choose, "chosen"));
		assertTrue(index(choose, "stances") < index(choose, "columns"));
		assertFalse(calls(choose).contains("limit"), "Do not give up after only the first 32 chests");
		boolean loadedOnly = false;
		for (AbstractInsnNode insn : choose.instructions) if (insn instanceof MethodInsnNode call && call.name.equals("getChunk")) {
			AbstractInsnNode previous = call.getPrevious();
			while (previous != null && previous.getOpcode() < 0) previous = previous.getPrevious();
			loadedOnly = previous != null && previous.getOpcode() == org.objectweb.asm.Opcodes.ICONST_0;
		}
		assertTrue(loadedOnly, "Missing chunks must not be force-loaded");
	}
	@Test void confirmedCargoAuditRecordsCapacityAndBothHalvesOfLargeChest() throws Exception {
		var capacity = calls(method("BorerAreaCargo", "rememberCapacity"));
		assertTrue(capacity.contains("of")); assertTrue(capacity.contains("otherHalf"));
		assertEquals(2, capacity.stream().filter("remember"::equals).count());
		assertTrue(calls(method("BorerAreaCargo", "tick")).contains("rememberCapacity"));
	}
	@Test void cargoPreflightsNewPlacementVisibilityAndPreservesNormalInteraction() throws Exception {
		assertTrue(calls(method("BorerAreaCargo", "chooseDepot")).contains("canPlaceFrom"));
		assertTrue(calls(method("BorerAreaCargo", "canPlaceFrom")).containsAll(List.of("clip", "getDirection")));
		assertTrue(calls(method("BorerAreaCargo", "clickBlock")).contains("useItemOn"));
	}
	@Test void sceneryIsDispatchedBeforeMiningFoodAndWornPickChecks() throws Exception {
		var tick = method("DefaultTunnelBorerEngine", "tick");
		int scenery = -1, mining = -1, i = 0;
		for (AbstractInsnNode insn : tick.instructions) {
			if (insn instanceof MethodInsnNode call && call.owner.endsWith("/SceneryExplorer") && call.name.equals("tick")) scenery = i;
			if (insn instanceof MethodInsnNode call && call.name.equals("pauseForMeteorFood")) mining = i;
			i++;
		}
		assertTrue(scenery >= 0 && mining > scenery);
		assertTrue(calls(method("DefaultTunnelBorerEngine", "stop")).contains("stop"));
	}
	@Test void sceneryNeverMinesPlacesConsumesFoodOrChangesHotbarAndExistingTargets() throws Exception {
		for (MethodNode method : node("SceneryExplorer").methods) {
			for (String call : calls(method)) assertFalse(List.of("startDestroyBlock", "continueDestroyBlock", "useItemOn", "attack", "setSelectedSlot", "handleContainerInput", "setBorerLastMode", "saveSettings").contains(call), call);
			assertFalse(fields(method).contains("keyUse"), "Meteor AutoEat retains Use ownership");
		}
	}
	@Test void sceneryOnlySubmitsRealLoadedLitChunksAndPersistsAfterBatchCommit() throws Exception {
		var observe = calls(method("SceneryExplorer", "observeOne"));
		assertTrue(observe.indexOf("getChunk") < observe.indexOf("lightOnInColumn"));
		assertTrue(observe.indexOf("isReal") < observe.indexOf("lightOnInColumn"));
		assertTrue(observe.indexOf("ready") < observe.indexOf("accept"));
		assertTrue(observe.indexOf("accept") < observe.indexOf("accepted"));
		var tick = calls(method("SceneryExplorer", "tick"));
		assertTrue(tick.indexOf("commitBatch") < tick.indexOf("write"));
	}
	@Test void lightChecksUseSectionColumnEncodingInsteadOfTheIncompatibleChunkPacking() throws Exception {
		for (String name : List.of("observeOne", "captureWait", "show")) {
			var calls = calls(method("SceneryExplorer", name));
			assertTrue(calls.indexOf("lightColumnKey") >= 0 && calls.indexOf("lightColumnKey") < calls.indexOf("lightOnInColumn"));
			assertFalse(calls.contains("pack"), "ChunkPos.pack is not a light-column key");
		}
		assertTrue(calls(method("SceneryCapturePolicy", "lightColumnKey")).contains("getZeroNode"));
	}
	@Test void sceneryUsesServerViewAndRejectsFakeTerrainForCaptureAndFlight() throws Exception {
		assertTrue(calls(method("SceneryExplorer", "observe")).contains("scan"));
		assertFalse(calls(method("SceneryExplorer", "observe")).contains("renderDistance"));
		assertTrue(calls(method("SceneryExplorer", "terrain")).contains("isReal"));
		assertTrue(calls(method("SceneryExplorer", "safeStep")).contains("isReal"));
		assertTrue(calls(method("SceneryBobby", "isReal")).containsAll(List.of("getLevel", "isInstance")));
	}
	@Test void bobbyWritesOnItsNativeQueueAndDoesNotInstallTheReturnedFakeChunk() throws Exception {
		assertTrue(fields(method("SceneryBobby", "accept")).contains("nativeSave"));
		assertTrue(calls(method("SceneryBobby", "accept")).contains("invoke"));
		for (AbstractInsnNode insn : method("SceneryBobby", "accept").instructions)
			if (insn instanceof MethodInsnNode call) assertNotEquals("java/util/function/Supplier", call.owner);
		assertTrue(calls(method("SceneryBobby$1", "afterSaves")).contains("execute"));
		assertTrue(calls(method("SceneryBobby$1", "flush")).contains("synchronize"));
		assertTrue(calls(method("SceneryBobby$1", "read")).contains("read"));
		var tick = calls(method("SceneryExplorer", "tick"));
		assertTrue(tick.indexOf("batchCommitted") < tick.indexOf("commitBatch"));
	}
	@Test void completedOrStoppedAreaHidesOutlineAndSavedLastModeCannotRedrawIt() throws Exception {
		var stop = method("DefaultTunnelBorerEngine", "stop"); boolean clears = false;
		for (AbstractInsnNode insn : stop.instructions) if (insn instanceof FieldInsnNode f && f.name.equals("areaOutlineVisible") && f.getOpcode() == org.objectweb.asm.Opcodes.PUTFIELD) {
			AbstractInsnNode value = f.getPrevious(); while (value != null && value.getOpcode() < 0) value = value.getPrevious();
			clears = value != null && value.getOpcode() == org.objectweb.asm.Opcodes.ICONST_0;
		}
		assertTrue(clears); assertTrue(calls(method("BorerAreaRunner", "stop")).contains("stop"));
		for (String method : List.of("presentAreaIfNeeded", "emitAreaPreviewGizmosIfNeeded")) assertFalse(calls(method("BorerPreview", method)).contains("borerLastMode"));
		assertTrue(calls(method("BorerPreview", "emitAreaPreviewGizmosIfNeeded")).contains("visible"));
	}
	@Test void dismissAreaIsVisualOnlyAndDoesNotInvokeTheOldNavigationReset() throws Exception {
		var hide = method("DefaultTunnelBorerEngine", "dismissAreaPreview");
		assertTrue(calls(hide).isEmpty());
		for (AbstractInsnNode insn : hide.instructions) if (insn instanceof FieldInsnNode f && f.getOpcode() == org.objectweb.asm.Opcodes.PUTFIELD)
			assertTrue(List.of("areaOutlineVisible", "showingAreaPreview").contains(f.name));
	}
	private static ClassNode node(String name) throws Exception {
		ClassNode node = new ClassNode();
		try (var in = BorerAutomationWiringTest.class.getResourceAsStream("/dev/twob2tkit/runtime/engine/" + name + ".class")) {
			assertNotNull(in); new ClassReader(in).accept(node, 0);
		}
		return node;
	}
	private static MethodNode method(String type, String name) throws Exception {
		return node(type).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
	}
	private static List<String> calls(MethodNode method) {
		List<String> calls = new ArrayList<>();
		for (AbstractInsnNode insn : method.instructions) if (insn instanceof MethodInsnNode call) calls.add(call.name);
		return calls;
	}
	private static List<String> fields(MethodNode method) {
		List<String> fields = new ArrayList<>();
		for (AbstractInsnNode insn : method.instructions) if (insn instanceof FieldInsnNode field) fields.add(field.name);
		return fields;
	}
	private static int index(MethodNode method, String name) {
		int index = calls(method).indexOf(name); assertTrue(index >= 0, "Missing call: " + name); return index;
	}
}
