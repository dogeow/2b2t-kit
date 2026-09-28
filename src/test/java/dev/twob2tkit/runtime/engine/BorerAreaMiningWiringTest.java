package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaMiningWiringTest {
    private MethodNode method(String type,String name)throws Exception{
        ClassNode node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+type+".class")){new ClassReader(in).accept(node,0);}
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method){List<String> names=new ArrayList<>();for(var n:method.instructions)if(n instanceof MethodInsnNode m)names.add(m.name);return names;}
    @Test void areaMiningHasNativeStartAndContinueAfterVerifyingTheActualRay()throws Exception{
        var calls=calls(method("runtime/engine/BorerAreaRunner","mine"));
        assertTrue(calls.indexOf("clipView")<calls.indexOf("startObservedBreak"));
        assertTrue(calls.contains("continueDestroyBlock"));assertTrue(calls.contains("directMiningSupported"));
        assertTrue(calls(method("mixin/MinecraftTickMixin","kit$ownedMining")).contains("borer"));
        assertTrue(calls(method("borer/TunnelBorer","ownsMining")).contains("ownsMining"));
    }
    @Test void areaClickRegistersVanillaPredictionBeforeMeteorCanRemoveTheLocalBlock()throws Exception{
        var c=calls(method("runtime/engine/BorerMiningConfirmation","startObservedBreak"));
        assertTrue(c.indexOf("startPredicting")<c.indexOf("startDestroyBlock"));assertTrue(c.contains("close"));
        assertFalse(c.contains("endPredictionsUpTo"));assertFalse(c.contains("updateKnownServerState"));assertFalse(c.contains("setBlock"));
    }
    @Test void pendingBurstIsHandledBeforePlanningAnyMovementAndCandidateRaysRemainVerified()throws Exception{
        var c=calls(method("runtime/engine/BorerAreaRunner","tick"));
        assertTrue(c.indexOf("tickPipeline")<c.indexOf("step"));
        var burst=calls(method("runtime/engine/BorerAreaRunner","tickPipelineWork"));
        assertTrue(burst.containsAll(List.of("pipelineAllowed","wouldOpenWater","wouldOpenLava","blocksRay","clipView","allows")));
        assertFalse(burst.contains("move"));
    }
    @Test void predictedAirCannotBeCountedAsACompletedAreaCell()throws Exception{
        var calls=calls(method("runtime/engine/BorerAreaRunner","cell"));
        assertTrue(calls.indexOf("pending")>=0&&calls.indexOf("pending")<calls.indexOf("isAir"));
    }
    @Test void preparationChecksDoNotWriteToChat()throws Exception{
        for(String name:List.of("beforeStart","tick","refresh"))assertFalse(calls(method("adventure/MiningChecklist",name)).contains("sendSystemMessage"));
    }
    @Test void cargoUsesTheChecklistSuppliesFromTheHostBeforeSelectingAnyStack()throws Exception{
        assertTrue(calls(method("runtime/engine/BorerAreaCargo","bag")).contains("borerCargoSupplies"));
        assertTrue(calls(method("borer/TunnelBorer$HostBridge","borerCargoSupplies")).contains("reserved"));
        var supplyCalls=calls(method("adventure/MiningCargoSupplies","reserved"));
        assertTrue(supplyCalls.containsAll(List.of("ensureLists","findList","requirements","reserve")));
    }
    @Test void depotSelectionUsesTheSameBroadCargoPolicyAsActualTransfer()throws Exception{
        assertTrue(calls(method("runtime/engine/BorerAreaCargo","chooseDepot")).contains("depositable"));
        assertTrue(calls(method("runtime/engine/BorerCargoPolicy","depositable")).contains("material"),"Legacy host still has its conservative fallback");
    }
    @Test void actualPipelineUsesInstantRebreakAndKeepsScanningWhenFirstAckArrivesEarly()throws Exception{
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","fastClick")).contains("repeatClick"));
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","clickPipeline")).contains("finishRepeat"));
        var c=calls(method("runtime/engine/BorerAreaRunner","tickPipelineWork"));
        assertTrue(c.contains("finishRepeat"));assertTrue(c.indexOf("active")>c.indexOf("clickPipeline"));
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","holdForMining")).contains("digOnFoot"));
    }
    @Test void miningCanAdvanceWithoutSurrenderingItsCameraButChecksClearanceBeforeKeys()throws Exception{
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","tickPipeline")).contains("advanceWhileMining"));
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","mine")).contains("advanceWhileMining"));
        var c=calls(method("runtime/engine/BorerAreaRunner","advanceWhileMining"));
        assertTrue(c.indexOf("safe")<c.indexOf("setDown"));assertTrue(c.contains("miningAdvanced"));
        assertFalse(c.contains("apply"));assertFalse(c.contains("setDeltaMovement"));
    }
    @Test void runtimeLogVersionIsGeneratedFromTheSameReleaseProperty()throws Exception{
        var p=new java.util.Properties();try(var in=java.nio.file.Files.newInputStream(java.nio.file.Path.of("gradle.properties"))){p.load(in);}
        assertEquals(p.getProperty("runtime_engine_version"),EngineBuildVersion.VALUE);
    }
    @Test void everyJevAnswerIsRecordedWhileAreaMiningRemainsPaused()throws Exception{
        var entry=calls(method("runtime/engine/DefaultTunnelBorerEngine","tickArea"));
        assertTrue(entry.contains("tick"));
        assertFalse(entry.contains("handle"),"AREA must not start the legacy Think/Grok movement owner");
        var stall=calls(method("runtime/engine/BorerAreaRunner","enterStall"));
        assertTrue(stall.indexOf("suspend")>=0 && stall.indexOf("suspend")<stall.indexOf("consult"));
        var advice=method("runtime/engine/BorerAreaRunner","recordStallAdvice");
        var callbacks=calls(advice);
        assertTrue(callbacks.containsAll(List.of("receipt","outcome")));
        assertFalse(callbacks.contains("choice"),"No model choice may branch to an action");
        assertFalse(callbacks.contains("rescanAfterStall"));
        assertFalse(callbacks.contains("startRecovery"));
        assertFalse(callbacks.contains("mine"));
        assertFalse(callbacks.contains("move"));
        assertFalse(callbacks.contains("stop"));
        for(var instruction:advice.instructions)
            if(instruction instanceof FieldInsnNode field)
                assertFalse(field.getOpcode()==org.objectweb.asm.Opcodes.PUTFIELD && field.name.equals("stallHold"));
        var hold=calls(method("runtime/engine/BorerAreaRunner","tickStallHold"));
        assertTrue(hold.containsAll(List.of("holdWithoutCheckpoint","safeForAdvice","ownsHoverLease")));
        assertFalse(hold.contains("checkpoint"),"Idle hold must not rewrite area progress every tick");
        assertFalse(hold.contains("rescanAfterStall"));
        assertFalse(hold.contains("mine"));
        assertFalse(hold.contains("move"));
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","manualMovementHeld")).contains("glfwGetMouseButton"));
        assertFalse(calls(method("runtime/engine/BorerAreaRunner","safeForAdvice")).contains("isWindowActive"),
            "Unfocused, safe incidents may still get anonymous advice");
    }
    @Test void onlyExplicitRestartCanProduceAnActualFollowupOutcome()throws Exception{
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","releaseFlight")).contains("outcome"));
        var followup=calls(method("runtime/engine/BorerAreaRunner","observeFollowup"));
        assertTrue(followup.contains("finishFollowup"));
        assertFalse(calls(method("runtime/engine/BorerAreaRunner","recordStallAdvice")).contains("finishFollowup"));
    }

}
