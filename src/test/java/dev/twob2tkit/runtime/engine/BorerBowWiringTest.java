package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

/** Inspect real bytecode hooks without initializing Minecraft's client singleton. */
class BorerBowWiringTest {
    private static final String ROOT = "dev/twob2tkit/";
    @Test void cameraHookTargetsExistingGameMethodAndRunsAtTail() throws Exception {
        assertNotNull(method("net/minecraft/client/Camera", "alignWithEntity", "(F)V"));
        assertNotNull(method("net/minecraft/client/Camera", "setRotation", "(FF)V"));
        var hook = method(ROOT + "mixin/BorerCombatCameraMixin", "kit$visibleCombatAim");
        var calls = calls(hook);
        assertTrue(calls.indexOf("isFirstPerson") < calls.indexOf("setRotation"));
        assertTrue(calls.indexOf("isActive") < calls.indexOf("setRotation"));
        assertTrue(calls.indexOf("setRotation") < calls.indexOf("combatViewRendered"));
        assertTrue(annotations(hook).contains("TAIL"));
    }
    @Test void actualReleaseIsCancellableBeforeVanillaSendsUsePacket() throws Exception {
        assertNotNull(method("net/minecraft/client/multiplayer/MultiPlayerGameMode", "releaseUsingItem", "(Lnet/minecraft/world/entity/player/Player;)V"));
        var hook = method(ROOT + "mixin/MultiPlayerGameModeMixin", "kit$visibleBowRelease");
        assertTrue(calls(hook).containsAll(List.of("prepareBowRelease", "cancel")));
        assertTrue(annotations(hook).contains("HEAD"));
        assertTrue(annotations(hook).contains("cancellable, true"));
    }
    @Test void releaseResolvesCurrentTrajectoryAndChecksVisibleFrameBeforeSendingRotation() throws Exception {
        var release = calls(method(ROOT + "runtime/engine/BorerRangedCombat", "prepareRelease"));
        assertTrue(release.indexOf("borerBowAim") < release.indexOf("viewReady"));
        assertTrue(release.indexOf("apply") < release.indexOf("send"));
        assertTrue(release.indexOf("viewReady") < release.indexOf("send"));
        assertTrue(release.indexOf("send") < release.indexOf("borerBowDiagnostics"));
        var tick = method(ROOT + "runtime/engine/BorerRangedCombat", "tick");
        assertFalse(calls(tick).contains("send"), "Scheduling key release is not a real shot");
    }
    @Test void activeCombatLookPrecedesStaleGhastOrMiningLook() throws Exception {
        var calls = calls(method(ROOT + "KitClient", "reapplyNavigationRotation"));
        assertTrue(calls.indexOf("borerCombatLook") < calls.indexOf("hasLook"));
        assertTrue(calls(method(ROOT + "piglin/PiglinBrawler", "tickGhastGuard")).contains("clearAim"));
    }
    @Test void manualBowsAndFoodRetainTheirOwnReleaseBehavior() throws Exception {
        var host = calls(method(ROOT + "KitClient", "prepareBowRelease"));
        assertTrue(host.indexOf("getUseItem") < host.indexOf("prepareBowRelease"));
        var release = method(ROOT + "runtime/engine/BorerRangedCombat", "prepareRelease");
        var meaningful = new ArrayList<AbstractInsnNode>();
        for (var i : release.instructions) if (i.getOpcode() >= 0) meaningful.add(i);
        assertTrue(meaningful.stream().limit(12).anyMatch(i -> i.getOpcode() == Opcodes.IRETURN), "No drawing or pending release must return before target/camera checks");
        for (String method : List.of("cancelDraw", "pauseForEating")) {
            var node = method(ROOT + "runtime/engine/BorerRangedCombat", method);
            assertTrue(calls(node).contains("reset"));
            assertTrue(writes(node).containsAll(List.of("drawing", "releasePending", "look")));
        }
    }
    @Test void oldHostCapabilityFailsClosedWithoutChangingApiVersion() throws Exception {
        var support = method(ROOT + "runtime/engine/BorerRangedCombat", "visibleHost");
        assertTrue(support.tryCatchBlocks.stream().anyMatch(c -> "java/lang/LinkageError".equals(c.type)));
        var fallback = method(ROOT + "runtime/api/BorerHost", "supportsVisibleBowAim");
        assertTrue((fallback.access & Opcodes.ACC_ABSTRACT) == 0);
        assertTrue(calls(fallback).isEmpty());
        assertTrue(calls(method(ROOT + "runtime/engine/BorerRangedCombat", "tick")).contains("visibleHost"));
    }
    @Test void damageProtectionDoesNotReenableAuraDuringOwnedBowAim() throws Exception {
        var calls = calls(method(ROOT + "combat/MeteorCombatAssist", "arm"));
        assertTrue(calls.indexOf("borerCombatLook") < calls.indexOf("enable"));
        assertTrue(calls(method(ROOT + "runtime/engine/BorerRangedCombat", "reapply")).contains("rangedMode"));
    }
    @Test void engagementAndPriorityRemainRequired() throws Exception {
        var clazz = node(ROOT + "runtime/engine/BorerRangedCombat");
        assertTrue(clazz.methods.stream().anyMatch(m -> calls(m).contains("shouldReact")));
        assertTrue(calls(method(ROOT + "runtime/engine/BorerRangedCombat", "rank")).contains("priority"));
    }
    @Test void constructionGuardReusesCombatWithoutStartingMiningOrAcquiringAreaFlight() throws Exception {
        var guard = calls(method(ROOT + "runtime/engine/DefaultTunnelBorerEngine", "tickStandaloneGuard"));
        assertTrue(guard.containsAll(List.of("update", "meal", "pauseForEating", "tick")));
        assertFalse(guard.contains("start"));
        assertFalse(guard.contains("suspendForCombat"));
        var pause = calls(method(ROOT + "runtime/engine/DefaultTunnelBorerEngine", "pauseGuardMovement"));
        assertTrue(pause.contains("stopDestroyBlock"));
        assertFalse(pause.contains("acquire"));
        assertFalse(pause.contains("start"));
    }
    @Test void combatOwnsInputBeforeWalkingMiningAndPrintProposals() throws Exception {
        var order = calls(method(ROOT + "KitClient", "tickNavigation"));
        assertTrue(order.indexOf("beforeGuard") < order.indexOf("beforeInput"));
        var guard = calls(method(ROOT + "automation/AutomationBridge", "beforeGuard"));
        assertTrue(guard.indexOf("guard") < guard.indexOf("tickStandaloneGuard"));
        assertTrue(guard.contains("pause"));
        var print = calls(method(ROOT + "automation/ProfessionalPrinter", "tick"));
        assertTrue(print.indexOf("guardBusy") < print.indexOf("set"));
        assertTrue(calls(method(ROOT + "automation/ProfessionalPrinter", "allowNativeProposal")).contains("acquire"));
        assertTrue(calls(method(ROOT + "automation/ProfessionalPrinter", "pause")).contains("set"));
    }
    @Test void standaloneGuardIsOptionalForOldRuntimeAndStillUsesVisibleReleaseHook() throws Exception {
        var fallback = method(ROOT + "runtime/api/BorerEngine", "tickStandaloneGuard");
        assertTrue((fallback.access & Opcodes.ACC_ABSTRACT) == 0);
        assertTrue(calls(fallback).isEmpty());
        assertTrue(calls(method(ROOT + "runtime/engine/DefaultTunnelBorerEngine", "prepareBowRelease")).contains("prepareRelease"));
        assertTrue(calls(method(ROOT + "runtime/engine/DefaultTunnelBorerEngine", "combatViewRendered")).contains("viewRendered"));
    }
    private static ClassNode node(String name) throws Exception {
        var node = new ClassNode();
        try (var stream = BorerBowWiringTest.class.getResourceAsStream("/" + name + ".class")) {
            assertNotNull(stream, name); new ClassReader(stream).accept(node, 0);
        }
        return node;
    }
    private static MethodNode method(String type, String name) throws Exception {
        return node(type).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private static MethodNode method(String type, String name, String desc) throws Exception {
        return node(type).methods.stream().filter(m -> m.name.equals(name) && m.desc.equals(desc)).findFirst().orElseThrow();
    }
    private static List<String> calls(MethodNode method) {
        var result = new ArrayList<String>();
        for (var i : method.instructions) if (i instanceof MethodInsnNode call) result.add(call.name);
        return result;
    }
    private static List<String> writes(MethodNode method) {
        var result = new ArrayList<String>();
        for (var i : method.instructions) if (i instanceof FieldInsnNode field && field.getOpcode() == Opcodes.PUTFIELD) result.add(field.name);
        return result;
    }
    private static String annotations(MethodNode method) {
        var result = new StringBuilder();
        if (method.visibleAnnotations != null) for (var a : method.visibleAnnotations) append(result, a);
        if (method.invisibleAnnotations != null) for (var a : method.invisibleAnnotations) append(result, a);
        return result.toString();
    }
    private static void append(StringBuilder result, Object value) {
        if (value instanceof AnnotationNode a) append(result, a.values);
        else if (value instanceof List<?> list) for (Object item : list) { append(result, item); result.append(", "); }
        else result.append(value);
    }
}
