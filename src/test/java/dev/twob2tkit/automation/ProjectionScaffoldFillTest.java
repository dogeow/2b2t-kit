package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionScaffoldFillTest {
    @Test void twoPendingRequireAggregateDeltaAndBothIndependentServerAcknowledgements() {
        var window=new ProjectionScaffoldFill.AckWindow();
        assertTrue(window.sent("a","cobble"));assertTrue(window.sent("b","cobble"));
        assertFalse(window.sent("c","cobble"));assertEquals(2,window.pending());
        assertTrue(window.acknowledge("a","cobble",10));
        assertTrue(window.observe(128,126,Map.of("a",true,"b",true),10));
        assertTrue(window.observe(128,126,Map.of("a",true,"b",true),18));
        assertEquals(1,window.settled());assertEquals(1,window.pending());
        assertTrue(window.acknowledge("b","cobble",20));
        assertTrue(window.observe(128,126,Map.of("a",true,"b",true),20));
        assertTrue(window.observe(128,126,Map.of("a",true,"b",true),27));assertEquals(1,window.pending());
        assertTrue(window.observe(128,126,Map.of("a",true,"b",true),28));assertEquals(0,window.pending());
    }
    @Test void predictedStatesAndDeltaAloneNeverConfirmEitherCell() {
        var window=new ProjectionScaffoldFill.AckWindow();window.sent("a","cobble");window.sent("b","cobble");
        assertTrue(window.observe(128,126,Map.of("a",true,"b",true),50));
        assertEquals(2,window.pending());assertEquals(0,window.settled());
    }
    @Test void correctionOrOverspendingClosesEveryUnsentSlot() {
        var corrected=new ProjectionScaffoldFill.AckWindow();corrected.sent("a","cobble");corrected.sent("b","cobble");
        assertTrue(corrected.acknowledge("a","cobble",10));
        assertFalse(corrected.acknowledge("a","air",11));assertFalse(corrected.canSend());
        assertFalse(corrected.sent("c","cobble"));
        var shortage=new ProjectionScaffoldFill.AckWindow();shortage.sent("a","cobble");shortage.sent("b","cobble");
        assertFalse(shortage.observe(128,125,Map.of("a",true,"b",true),10));assertFalse(shortage.canSend());
    }
    @Test void fourteenSentThirteenSettledAllowsOneLateInventorySyncAndLateAckWithoutResending() {
        var window=new ProjectionScaffoldFill.AckWindow();var states=new LinkedHashMap<String,Boolean>();
        settleThirteen(window,states);
        assertTrue(window.sent("14","cobble",140));states.put("14",true);
        assertTrue(window.observe(204,191,states,141));
        assertEquals(13,window.settled());assertEquals(1,window.pending());
        assertTrue(window.inventoryPending());assertFalse(window.canSend());assertFalse(window.sent("15","cobble",142));
        assertTrue(window.acknowledge("14","cobble",146));
        assertTrue(window.observe(204,190,states,147));
        assertEquals(13,window.settled());assertTrue(window.inventoryPending());assertFalse(window.canSend());
        assertTrue(window.observe(204,190,states,154));assertEquals(1,window.pending());
        assertTrue(window.observe(204,190,states,155));assertEquals(14,window.settled());
        assertEquals(0,window.pending());assertFalse(window.inventoryPending());assertTrue(window.canSend());
        assertFalse(window.sent("14","cobble",156));
    }
    @Test void twoUnsettledCellsMayLagButNeedExactInventoryAndBothAcksBeforeRecoveryOpens() {
        var window=new ProjectionScaffoldFill.AckWindow();window.sent("a","cobble",0);window.sent("b","cobble",1);
        var states=Map.of("a",true,"b",true);
        assertTrue(window.observe(128,128,states,2));assertFalse(window.canSend());
        window.acknowledge("a","cobble",3);
        assertTrue(window.observe(128,127,states,10));assertEquals(0,window.settled());
        assertTrue(window.observe(128,126,states,11));
        assertTrue(window.observe(128,126,states,19));assertEquals(1,window.settled());assertFalse(window.canSend());
        window.acknowledge("b","cobble",20);
        assertTrue(window.observe(128,126,states,20));
        assertTrue(window.observe(128,126,states,27));assertFalse(window.canSend());
        assertTrue(window.observe(128,126,states,28));assertEquals(0,window.pending());assertTrue(window.canSend());
    }
    @Test void settledInventoryRollbackIsNeverTreatedAsPendingLag() {
        var window=new ProjectionScaffoldFill.AckWindow();var states=new LinkedHashMap<String,Boolean>();
        settleThirteen(window,states);window.sent("14","cobble",140);states.put("14",true);
        assertFalse(window.observe(204,192,states,141));assertFalse(window.canSend());
    }
    @Test void lagBeyondTheTwoCellWindowAndUnknownWorldStateFailClosed() {
        var tooLarge=new ProjectionScaffoldFill.AckWindow();tooLarge.sent("a","cobble");tooLarge.sent("b","cobble");
        assertFalse(tooLarge.observe(128,129,Map.of("a",true,"b",true),10));assertFalse(tooLarge.canSend());
        var unknown=new ProjectionScaffoldFill.AckWindow();unknown.sent("a","cobble");unknown.sent("b","cobble");
        assertFalse(unknown.observe(128,127,Map.of("a",true),10));assertFalse(unknown.canSend());
    }
    @Test void inventoryLagStillTimesOutAtOneHundredTicksAndCannotRecoverAfterward() {
        var window=new ProjectionScaffoldFill.AckWindow();window.sent("a","cobble",20);
        assertTrue(window.observe(128,128,Map.of("a",true),119));
        assertFalse(window.observe(128,128,Map.of("a",true),120));assertFalse(window.canSend());
        assertFalse(window.acknowledge("a","cobble",121));
        assertFalse(window.observe(128,127,Map.of("a",true),130));
    }
    @Test void correctedCubeDuringInventoryRecoveryNeverCountsAsSuccess() {
        var window=new ProjectionScaffoldFill.AckWindow();window.sent("a","cobble",0);
        assertTrue(window.observe(128,128,Map.of("a",true),1));window.acknowledge("a","cobble",2);
        assertFalse(window.observe(128,127,Map.of("a",false),10));assertEquals(0,window.settled());assertFalse(window.canSend());
    }
    private static void settleThirteen(ProjectionScaffoldFill.AckWindow window,Map<String,Boolean> states) {
        for(int i=1;i<=13;i++){
            String key=Integer.toString(i);long tick=i*10;
            assertTrue(window.sent(key,"cobble",tick));states.put(key,true);
            assertTrue(window.acknowledge(key,"cobble",tick));
            assertTrue(window.observe(204,204-i,states,tick));
            assertTrue(window.observe(204,204-i,states,tick+8));
        }
        assertEquals(13,window.settled());assertEquals(0,window.pending());
    }
    @Test void settledCellsStillCannotBeResentAndLaterWorldCorrectionInvalidatesTheWindow() {
        var window=new ProjectionScaffoldFill.AckWindow();window.sent("a","cobble");window.acknowledge("a","cobble",10);
        assertTrue(window.observe(128,127,Map.of("a",true),10));
        assertTrue(window.observe(128,127,Map.of("a",true),18));assertFalse(window.sent("a","cobble"));
        assertFalse(window.observe(128,127,Map.of("a",false),19));assertFalse(window.canSend());
    }
    @Test void callbacksDoNotInventAcknowledgementsForUnknownTargets() {
        var window=new ProjectionScaffoldFill.AckWindow();window.sent("a","cobble");
        assertFalse(window.acknowledge("old","cobble",10));
        assertTrue(window.observe(128,127,Map.of("a",true),30));assertEquals(1,window.pending());
    }
    @Test void placementGateRunsBeforeAutoswitchAndObserverBeforeOrdinaryPrediction()throws Exception {
        var target=Files.readString(Path.of("src/client/java/dev/twob2tkit/mixin/MeteorScaffoldTargetMixin.java"));
        var interaction=Files.readString(Path.of("src/client/java/dev/twob2tkit/mixin/MultiPlayerGameModeMixin.java"));
        var modules=Files.readString(Path.of("src/client/java/dev/twob2tkit/mixin/MeteorScaffoldModuleLifecycleMixin.java"));
        assertTrue(target.contains("place(Lnet/minecraft/core/BlockPos;)Z"));assertTrue(target.contains("at=@At(\"HEAD\"),cancellable=true"));
        assertTrue(target.contains("implements ProjectionScaffoldFill.GateInstalled"));
        assertTrue(interaction.indexOf("prepareProjectionScaffoldInteraction")<interaction.indexOf("ProfessionalPrinter.prepareInteraction"));
        assertTrue(modules.contains("toggle()V"));assertTrue(modules.contains("projectionScaffoldModuleToggleObserved(this)"));
    }
    @Test void controllerUsesDedicatedNormalFlightAndNeverTeleportsOrWritesWorldBlocks()throws Exception {
        var source=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/ProjectionScaffoldFill.java"));
        assertFalse(source.contains("setPos("));assertFalse(source.contains("setDeltaMovement("));assertFalse(source.contains("setBlock("));
        assertFalse(source.contains("BorerAreaFlightSession"));assertFalse(source.contains("controller().start"));
        assertTrue(source.contains("currentStates"));assertTrue(source.contains("cumulativeInventoryMatches"));
        assertTrue(source.contains("ProjectionScaffoldPolicy.windowAvailable(pending())"));
        assertTrue(source.contains("loaded server"));
        assertTrue(source.contains("baselineCurrent(c)"));assertTrue(source.contains("serverChunk(c,attempt.pos)"));
        assertTrue(source.contains("if(ackWindow.inventoryPending()){stage=\"awaiting_inventory_sync\";stopPlacement(c);}"));
    }
    @Test void bridgeUsesLiveHeartbeatAndRetainsMapAndSingleSeedProtocols()throws Exception {
        var source=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/AutomationBridge.java"));
        assertTrue(source.contains("System.currentTimeMillis()-lastSupervisionHeartbeat>15000"));
        assertTrue(source.contains("projection_scaffold_fill_protocol"));assertTrue(source.contains("map_audit_protocol"));
        assertTrue(source.contains("projection_air_seed_protocol"));assertTrue(source.contains("scaffoldFillTask.serverBlock(c,pos,packetState,applied,ticks)"));
    }
    @Test void physicalRightClickCancelsOwnershipAndReachesVanillaInsteadOfBeingSwallowed()throws Exception {
        var source=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/AutomationBridge.java"));
        int begin=source.indexOf("public static boolean prepareProjectionScaffoldInteraction");
        int end=source.indexOf("public static void projectionScaffoldModuleToggleObserved",begin);
        String method=source.substring(begin,end);
        assertTrue(method.indexOf("KitKeys.isPhysicallyDown(c,c.options.keyUse)")<method.indexOf("scaffoldFillTask.prepareInteraction"));
        assertTrue(method.contains("cancelWork(c,\"Manual right-click cancelled"));
        assertTrue(method.contains("return false; // Let the user's first real click reach vanilla"));
    }
}
