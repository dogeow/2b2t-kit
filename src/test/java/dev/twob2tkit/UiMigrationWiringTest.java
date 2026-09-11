package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Assertions on the active new UI paths, rather than tests of retired legacy widget code. */
class UiMigrationWiringTest {
    @Test void nativeAndCompactEntryPointsShareTheSameWorkspace() throws Exception {
        assertEquals("dev/twob2tkit/KitWorkspaceScreen", node("ClickGuiScreen").superName);
        assertTrue(types(method("KitTab", "home")).contains("dev/twob2tkit/KitWorkspaceScreen"));
        assertFalse(calls(method("KitTab", "home")).contains("create"));
    }
    @Test void workspaceOnlyNavigatesOrStopsAndNeverStartsAutomation() throws Exception {
        for (MethodNode m : node("KitWorkspaceScreen").methods)
            for (String call : calls(m)) assertFalse(List.of("start", "toggle", "resume", "toggleBorer", "toggleCruiseFromKey").contains(call), m.name + ":" + call);
        assertTrue(node("KitWorkspaceScreen").methods.stream().anyMatch(m -> calls(m).contains("open")));
    }
    @Test void oldFunctionScreensRedirectBeforeTheirOldWidgetsAreBuilt() throws Exception {
        for (String type : List.of("KitScreen", "SettingsHomeScreen", "GuardHomeScreen", "DeathPointScreen", "KitSavedPlacesScreen", "KitTrustedPlayersScreen",
                "chopper/ChopperScreen", "planter/PlanterScreen", "feeder/FeederScreen", "fisher/FisherScreen", "surround/SurroundScreen",
                "survival/SurvivalAlertsScreen", "piglin/PiglinBrawlerScreen", "cruise/CruiseOptionsScreen", "borer/BorerSafetyScreen",
                "SceneryScreen", "TechHomeScreen", "borer/BorerRouteScreen", "villager/VillagerScanScreen", "storage/StorageRecordsScreen",
                "structure/StructureMarksScreen", "adventure/ActivityChecklistScreen", "combat/HealingItemsScreen", "recipe/RecipeGuideScreen")) {
            var m = method(type, "init"); assertEquals("redirect", calls(m).getFirst(), type);
        }
        assertEquals("projects", calls(method("borer/AreaProjectsScreen", "init")).getFirst());
        assertEquals("openUnifiedSearch", calls(method("structure/NearbyStructuresScreen", "init")).getFirst());
        assertEquals("openUnifiedEditor", calls(method("structure/StructureNoteScreen", "init")).getFirst());
    }
    @Test void stopBranchPrecedesAndBypassesInputValidation() throws Exception {
        boolean checked = false;
        for (MethodNode m : node("KitFormScreen").methods) if (m.name.startsWith("lambda$init$") && calls(m).contains("finishEdits")) {
            assertTrue(calls(m).indexOf("run") < calls(m).indexOf("finishEdits")); checked = true;
        }
        assertTrue(checked);
    }
    @Test void allFieldsAreValidatedBeforeTheSetterTransactionAndInvalidFieldIsRevealed() throws Exception {
        var calls = calls(method("KitFormScreen", "finishEdits"));
        assertTrue(calls.indexOf("accept") >= 0 && calls.indexOf("accept") < calls.indexOf("forEach"));
        assertTrue(calls.contains("reveal"));
        assertTrue(calls(method("KitFormScreen", "reveal")).containsAll(List.of("clear", "rebuildWidgets", "layoutWidgets", "setFocused")));
    }
    @Test void closingFormsOnlyStoresDraftAndNeverAppliesOrRunsActions() throws Exception {
        var removed = calls(method("KitFormScreen", "removed"));
        assertTrue(removed.indexOf("capture") < removed.indexOf("save"));
        for (String forbidden : List.of("finishEdits", "accept", "run", "start")) assertFalse(removed.contains(forbidden));
        assertTrue(calls(method("KitCollectionScreen", "removed")).containsAll(List.of("scrollAmount", "remember", "save")));
    }
    @Test void unFocusedEnterHasNoImplicitSubmitOnNewPages() throws Exception {
        for (String type : List.of("KitFormScreen", "KitCollectionScreen", "KitWorkspaceScreen", "KitConfirmScreen", "KitRecipePages$Detail")) {
            var m = method(type, "onEnterPressed"); assertTrue(calls(m).isEmpty(), type);
            assertTrue(Arrays.stream(m.instructions.toArray()).anyMatch(i -> i.getOpcode() == Opcodes.ICONST_0));
        }
    }
    @Test void collectionActionsRecheckAvailabilityAtClickAndRestoreSelectionAfterPopulate() throws Exception {
        var entry = node("KitCollectionScreen$Items$Entry");
        assertTrue(entry.methods.stream().anyMatch(m -> m.name.startsWith("lambda$") && calls(m).contains("test") && calls(m).contains("accept")));
        assertTrue(calls(method("KitCollectionScreen$Items", "populate")).contains("setSelected"));
        assertTrue(calls(method("KitCollectionScreen$Items$Entry", "selectEntry")).contains("setSelected"));
    }
    @Test void editingAPlaceNeverChangesTheCruiseDestinationOrStartsMovement() throws Exception {
        boolean checked = false;
        for (MethodNode m : node("KitRecordPages").methods) if (m.name.contains("placeEditor")) {
            checked = true;
            for (AbstractInsnNode i : m.instructions) {
                if (i instanceof FieldInsnNode f && f.getOpcode() == Opcodes.PUTFIELD)
                    assertFalse(List.of("targetX", "targetZ", "cruiseY", "hasTarget").contains(f.name));
                if (i instanceof MethodInsnNode call) assertFalse(List.of("start", "startDeathRecovery", "resume").contains(call.name));
            }
        }
        assertTrue(checked);
    }
    @Test void menuKeyboardDoesNotBypassVisibleActionsAndGameplayInputStillHasItsOriginalPath() throws Exception {
        var menu = calls(method("KitHudScreen", "keyPressed"));
        for (String forbidden : List.of("toggleBorer", "toggleFeeder", "toggleFisher", "toggleChopper", "goNetherPortal")) assertFalse(menu.contains(forbidden));
        assertTrue(menu.contains("emergencyStop"));
        var tick = method("KitClient", "onEndTick");
        assertTrue(Arrays.stream(tick.instructions.toArray()).anyMatch(i -> i instanceof TypeInsnNode type && type.getOpcode() == Opcodes.INSTANCEOF && type.desc.equals("dev/twob2tkit/KitHudScreen")));
        assertTrue(calls(tick).containsAll(List.of("toggleBorer", "toggleCruiseFromKey", "tick")));
    }
    @Test void newGenericPagesNeverWriteMovementAttackOrFlightKeys() throws Exception {
        for (String type : List.of("KitFormScreen", "KitCollectionScreen", "KitWorkspaceScreen", "KitConfirmScreen")) {
            for (MethodNode m : node(type).methods) {
                assertFalse(calls(m).contains("setDown")); assertFalse(calls(m).contains("setDeltaMovement"));
                for (AbstractInsnNode i : m.instructions) if (i instanceof FieldInsnNode f)
                    assertFalse(List.of("keyJump", "keyAttack", "keyUse", "flying").contains(f.name));
            }
        }
    }
    private static ClassNode node(String type) throws Exception {
        var node = new ClassNode();
        try (var stream = UiMigrationWiringTest.class.getResourceAsStream("/dev/twob2tkit/" + type + ".class")) {
            assertNotNull(stream, type); new ClassReader(stream).accept(node, 0);
        }
        return node;
    }
    private static MethodNode method(String type, String name) throws Exception { return node(type).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow(); }
    private static List<String> calls(MethodNode method) {
        List<String> calls = new ArrayList<>(); for (AbstractInsnNode i : method.instructions) if (i instanceof MethodInsnNode m) calls.add(m.name); return calls;
    }
    private static List<String> types(MethodNode method) {
        List<String> types = new ArrayList<>(); for (AbstractInsnNode i : method.instructions) if (i instanceof TypeInsnNode t) types.add(t.desc); return types;
    }
    @Test void fillButtonsChangeRawDraftOnlyAndRecordEditorsUseStableOriginalValues() throws Exception {
        var fill = method("KitFormScreen", "draftValue");
        assertTrue(calls(fill).containsAll(List.of("remember", "setValue")));
        assertFalse(calls(fill).contains("accept")); assertFalse(calls(fill).contains("save"));
        var source = method("KitFormScreen$Input", "source");
        assertTrue(Arrays.stream(source.instructions.toArray()).anyMatch(i -> i instanceof FieldInsnNode f && f.name.equals("origin")));
        assertTrue(calls(method("KitRecordPages", "placeEditor")).contains("recordDraft"));
        assertTrue(calls(method("structure/NearbyStructuresScreen", "openUnifiedSearch")).contains("recordDraft"));
    }
    @Test void workspaceUsesCompactGridAndActivePagesUseCappedFooterButtons() throws Exception {
        var grid = calls(method("KitWorkspaceScreen", "rebuildEntries"));
        assertTrue(grid.containsAll(List.of("of", "x", "y", "openWidth", "favoriteX", "contentHeight")));
        for (String type : List.of("KitWorkspaceScreen", "KitFormScreen", "KitCollectionScreen", "KitConfirmScreen", "KitKeyBindsScreen", "KitRecipePages$Detail", "borer/AreaSetupScreen")) {
            var init = calls(method(type, "init"));
            assertTrue(init.contains("footerButtonX"), type); assertTrue(init.contains("footerButtonWidth"), type);
        }
        assertTrue(calls(method("KitCollectionScreen", "init")).contains("buttonWidth"), "Dimension filters retain their full content width");
    }
}
