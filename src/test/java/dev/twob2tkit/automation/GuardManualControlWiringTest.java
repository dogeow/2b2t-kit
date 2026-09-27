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
    private record ReleasePath(AbstractInsnNode instruction,boolean released) {}
    /** Follow both real bytecode branches: every normal return must have released combat input. */
    private void assertEveryReturnReleased(MethodNode method,Set<String> releasers){
        var pending=new ArrayDeque<ReleasePath>();var visited=new HashSet<ReleasePath>();int returns=0;
        pending.add(new ReleasePath(method.instructions.getFirst(),false));
        while(!pending.isEmpty()){
            var path=pending.removeFirst();if(!visited.add(path))continue;
            var instruction=path.instruction();boolean released=path.released();
            if(instruction instanceof MethodInsnNode call&&call.owner.endsWith("/BorerRangedCombat")&&releasers.contains(call.name))released=true;
            int opcode=instruction.getOpcode();
            if(opcode>=Opcodes.IRETURN&&opcode<=Opcodes.RETURN){assertTrue(released,method.name+" returned without releasing combat controls");returns++;continue;}
            if(opcode==Opcodes.ATHROW)continue;
            if(instruction instanceof JumpInsnNode jump){pending.add(new ReleasePath(jump.label,released));if(opcode==Opcodes.GOTO)continue;}
            if(instruction.getNext()!=null)pending.add(new ReleasePath(instruction.getNext(),released));
        }
        assertTrue(returns>0,"No normal return was verified");
    }
    @Test void everyStopReasonUnconditionallyDisarmsBeforeWorkCleanup()throws Exception{
        var m=method("automation/AutomationBridge","cancel");var c=calls(m);
        assertEquals(List.of("stop","disarmGuard","reset","cancelWork"),c);
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
    @Test void verifiedUnderwaterAirReturnPreemptsCombatBeforeNavigationInput()throws Exception{
        var guard=calls(method("automation/AutomationBridge","beforeGuard"));
        assertTrue(guard.indexOf("ownedUnderwaterAirReturn")>=0
            &&guard.indexOf("ownedUnderwaterAirReturn")<guard.indexOf("tickStandaloneGuard"));
        assertTrue(guard.contains("suspendStandaloneCombatForAirReturn"));
        var escape=calls(method("automation/AutomationBridge","ownedUnderwaterAirReturn"));
        assertTrue(escape.containsAll(List.of("currentLease","underwaterAirReturn","getCollisionShape","getFluidState")));
        var suspension=calls(method("runtime/engine/DefaultTunnelBorerEngine","suspendStandaloneCombatForAirReturn"));
        assertTrue(suspension.containsAll(List.of("cancel","handoff")));
        assertTrue(suspension.indexOf("cancel")<suspension.indexOf("handoff"),"Cancel the older recovery controller before handing inputs to the owned air route");
        assertFalse(suspension.contains("tickStandaloneGuard"));
        var handoff=method("runtime/engine/BorerRangedCombat","handoff");
        assertTrue(calls(handoff).containsAll(List.of("retain","releaseControls","pause","save","end")));
        assertFalse(calls(handoff).contains("tick"));
        var end=method("runtime/engine/BorerRangedCombat","end");
        assertTrue(calls(end).contains("releaseControls"));
        assertEveryReturnReleased(end,Set.of("releaseControls"));
        // The safe-deferred branch retains UUIDs; the ordinary branch clears
        // them through end(). Both must yield inputs before returning success.
        assertEveryReturnReleased(handoff,Set.of("releaseControls","end"));
        var release=calls(method("runtime/engine/BorerRangedCombat","releaseControls"));
        assertTrue(release.containsAll(List.of("close","releaseEscape","cancelDraw","rangedMode")));
        assertFalse(release.contains("tick"));
    }
    @Test void materialAirWatchdogRunsBeforeCombatAndRetainsTheOwnedRequest()throws Exception{
        var guard=calls(method("automation/AutomationBridge","beforeGuard"));
        assertTrue(guard.indexOf("beginNativeAirReturn")>=0
            &&guard.indexOf("beginNativeAirReturn")<guard.indexOf("tickStandaloneGuard"));
        var rescue=calls(method("automation/AutomationBridge","beginNativeAirReturn"));
        assertTrue(rescue.containsAll(List.of("configuredJob","emergencyTarget","suspendAutoReconnect","startExact","keepConnectedOnArrival")));
        var tick=calls(method("automation/AutomationBridge","tick"));
        assertTrue(tick.containsAll(List.of("finishAscent","finish","safeLogout")));
        var snapshot=calls(method("automation/AutomationBridge","snapshot"));
        assertTrue(snapshot.contains("airEstimate"));
    }
    @Test void jumpAndAllMovementBindingsParticipateWithoutHardcodedWasd()throws Exception{
        var fields=new HashSet<String>();for(var n:method("KitKeys","movementKeys").instructions)if(n instanceof FieldInsnNode f)fields.add(f.name);
        assertTrue(fields.containsAll(List.of("keyJump","keyUp","keyDown","keyLeft","keyRight","keyShift","keySprint")));
        var c=calls(method("KitKeys","manualMovementDown"));
        assertTrue(c.containsAll(List.of("isWindowActive","isPhysicallyDown")));
        assertFalse(c.contains("isDown"),"Synthesized navigation keys must not trigger manual takeover");
    }
    @Test void appSwitchAndMouseDoNotTakeOverDirectionOnlyMaterialWork()throws Exception{
        var fields=new HashSet<String>();
        for(var n:method("KitKeys","takeoverKeys").instructions)if(n instanceof FieldInsnNode f)fields.add(f.name);
        assertTrue(fields.containsAll(Set.of("keyUp","keyDown","keyLeft","keyRight")));
        assertFalse(fields.contains("keyJump")||fields.contains("keyShift")||fields.contains("keySprint"));
        var manual=calls(method("KitKeys","manualMovementDown"));
        assertTrue(manual.contains("takeoverKeys"));
        assertFalse(manual.contains("glfwGetMouseButton"));
        assertTrue(calls(method("KitKeys","notePhysicalKey")).contains("takeoverKeys"));
        assertTrue(clazz("mixin/MouseHandlerMixin").methods.stream()
            .noneMatch(m->calls(m).contains("notePhysicalMouse")));
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
