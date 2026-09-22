package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Regressions for the actual tick/cancel wiring; no Minecraft server or player is required. */
class GuardManualControlWiringTest {
    private ClassNode clazz(String name)throws Exception{
        var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+name+".class")){
            assertNotNull(in);new ClassReader(in).accept(n,0);
        }return n;
    }
    private MethodNode method(String c,String n)throws Exception{return clazz(c).methods.stream().filter(m->m.name.equals(n)).findFirst().orElseThrow();}
    private List<String> calls(MethodNode m){var a=new ArrayList<String>();for(var n:m.instructions)if(n instanceof MethodInsnNode i)a.add(i.name);return a;}
    @Test void everyStopReasonUnconditionallyDisarmsBeforeWorkCleanup()throws Exception{
        var m=method("automation/AutomationBridge","cancel");var c=calls(m);
        assertEquals(List.of("stop","disarmGuard","cancelWork"),c);
        // The old root-button reason "工具箱停止全部" did not match contains("紧急停止").
        for(var n:m.instructions)assertFalse(n instanceof JumpInsnNode,"No translated reason may bypass cancellation");
    }
    @Test void disarmClearsScopeAndBusyAndEndsTheRuntimeGuardImmediately()throws Exception{
        var m=method("automation/AutomationBridge","disarmGuard");var fields=new ArrayList<String>();
        for(var n:m.instructions)if(n instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTSTATIC)fields.add(f.name);
        assertTrue(fields.containsAll(List.of("guardScope","guardBusy")));
        assertTrue(calls(m).contains("tickStandaloneGuard"));
    }
    @Test void physicalEmergencyAndMovementWinBeforeAnyGuardTick()throws Exception{
        var c=calls(method("KitClient","tickNavigation"));
        assertTrue(c.indexOf("handleHeldKeys")<c.indexOf("beforeGuard"));
        assertTrue(c.indexOf("yieldGuardToManualInput")<c.indexOf("beforeGuard"));
        var m=calls(method("automation/AutomationBridge","yieldGuardToManualInput"));
        assertTrue(m.indexOf("manualMovementDown")<m.indexOf("emergencyStop"));
    }
    @Test void jumpAndAllMovementBindingsParticipateWithoutHardcodedWasd()throws Exception{
        var fields=new HashSet<String>();for(var n:method("KitKeys","movementKeys").instructions)if(n instanceof FieldInsnNode f)fields.add(f.name);
        assertTrue(fields.containsAll(List.of("keyJump","keyUp","keyDown","keyLeft","keyRight","keyShift","keySprint")));
        var c=calls(method("KitKeys","manualMovementDown"));
        assertTrue(c.containsAll(List.of("isWindowActive","isPhysicallyDown")));
        assertFalse(c.contains("isDown"),"Synthesized navigation keys must not trigger manual takeover");
    }
    @Test void heldSpaceIsRestoredAfterAllTaskStopMethodsReleaseTheirInputs()throws Exception{
        assertEquals(List.of("stopAll"),calls(method("KitClient","emergencyStop")));
        var c=calls(method("KitClient","stopAll"));
        assertTrue(c.indexOf("cancel")<c.indexOf("stopWork"));
        assertTrue(c.indexOf("stopWork")<c.indexOf("restorePhysicalMovement"));
        var restore=calls(method("KitKeys","restorePhysicalMovement"));
        assertTrue(restore.indexOf("isPhysicallyDown")<restore.indexOf("setDown"));
    }
    @Test void startupCleanupIsSilentWhileRealEmergencyStopsStillAnnounce()throws Exception{
        for(var entry:Map.of("emergencyStop",Opcodes.ICONST_1,"toggleProjectionBuild",Opcodes.ICONST_0).entrySet()){
            MethodInsnNode call=null;
            for(var n:method("KitClient",entry.getKey()).instructions)if(n instanceof MethodInsnNode m&&m.name.equals("stopAll"))call=m;
            assertNotNull(call);var previous=call.getPrevious();while(previous.getOpcode()<0)previous=previous.getPrevious();
            assertEquals(entry.getValue().intValue(),previous.getOpcode());
        }
    }
    @Test void ordinaryGuardPauseAlsoPreservesPhysicalInputForOlderHosts()throws Exception{
        var c=calls(method("runtime/engine/DefaultTunnelBorerEngine","pauseGuardMovement"));
        assertTrue(c.indexOf("isKeyDown")>=0 && c.indexOf("isKeyDown")<c.indexOf("setDown"));
    }
    @Test void taskHandoffsCannotAccidentallyBehaveAsEmergencyStops()throws Exception{
        assertFalse(calls(method("automation/AutomationBridge","cancelWork")).contains("disarmGuard"));
        for(var n:method("KitClient","stopWork").instructions)if(n instanceof MethodInsnNode i && i.owner.endsWith("/AutomationBridge"))assertNotEquals("cancel",i.name);
        assertTrue(calls(method("KitClient","stopWork")).contains("cancelWork"));
    }
    @Test void rootStopAndCommandStopBothReachTheSameEmergencyPath()throws Exception{
        for(String cls:List.of("KitWorkspaceScreen","KitCommands"))
            assertTrue(clazz(cls).methods.stream().anyMatch(m->calls(m).contains("emergencyStop")),cls);
        assertTrue(clazz("KitClient").methods.stream().filter(m->m.name.startsWith("lambda$onInitializeClient"))
            .filter(m->calls(m).contains("emergencyStop")).count()>=2,"Disconnect and game exit must clean up standalone defense too");
    }
    @Test void depotMovementIsAppliedBeforeKeySamplingAndLookIsReappliedAfterMouse()throws Exception{
        assertTrue(calls(method("automation/AutomationBridge","beforeInput")).contains("input"));
        var c=calls(method("KitClient","reapplyNavigationRotation"));
        assertTrue(c.indexOf("reapplySupplyLook")>=0&&c.indexOf("reapplySupplyLook")<c.indexOf("reapplyNavigationRotation"));
        assertFalse(calls(method("automation/BuildSupplyTask","tick")).contains("move"));
    }
    @Test void internalRequestFailuresKeepTheSupervisedSafetyLeaseAvailable()throws Exception{
        var m=method("automation/AutomationBridge","abortOwnedRequest");
        assertTrue(calls(m).contains("stopWork"));
        for(var n:m.instructions)if(n instanceof FieldInsnNode f&&f.name.equals("supervisionLease"))assertNotEquals(Opcodes.PUTSTATIC,f.getOpcode());
        assertTrue(calls(method("automation/AutomationBridge","tick")).contains("abortOwnedRequest"));
    }
    @Test void intentionalLogoutSuppressesMeteorReconnectUntilAnotherJoin()throws Exception{
        var c=calls(method("automation/AutomationBridge","tickSupervision"));
        assertTrue(c.indexOf("suspendAutoReconnect")<c.indexOf("safeLogout"));
        assertTrue(calls(method("automation/AutomationBridge","suspendAutoReconnect")).contains("disable"));
        assertTrue(calls(method("automation/AutomationBridge","joined")).contains("enable"));
    }
    @Test void nativeDisconnectIsConfirmedBeforeCleanupErasesItsPendingReceipt()throws Exception{
        var callback=clazz("KitClient").methods.stream().filter(m->m.name.startsWith("lambda$onInitializeClient"))
            .filter(m->calls(m).contains("disconnected")).findFirst().orElseThrow();
        var c=calls(callback);assertTrue(c.indexOf("disconnected")<c.indexOf("emergencyStop"));
        assertTrue(calls(method("automation/AutomationBridge","disconnected")).contains("safetyReceipt"));
    }
}
