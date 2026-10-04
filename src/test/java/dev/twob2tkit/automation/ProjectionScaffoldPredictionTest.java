package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionScaffoldPredictionTest {
    private static final String BLOCK="Block{minecraft:sandstone}";
    private static Map<String,ProjectionScaffoldFill.AckWindow.Observation> observation(Boolean pending,boolean matches,boolean loaded){
        return Map.of("a",new ProjectionScaffoldFill.AckWindow.Observation(pending,matches,loaded));
    }
    private static ProjectionScaffoldFill.AckWindow window(){
        var w=new ProjectionScaffoldFill.AckWindow();assertTrue(w.sent("a",BLOCK,0));return w;
    }
    @Test void unappliedExpectedPacketWaitsForPredictionClearThenSevenIsNotEight(){
        var w=window();assertTrue(w.packet("a",BLOCK,true,false,10));
        assertTrue(w.observeProof(49,48,observation(true,false,true),10));assertEquals(0,w.settled());
        assertTrue(w.observeProof(49,48,observation(false,true,true),20));assertEquals(0,w.settled());
        assertTrue(w.observeProof(49,48,observation(false,true,true),27));assertEquals(0,w.settled());
        assertTrue(w.observeProof(49,48,observation(false,true,true),28));assertEquals(1,w.settled());
        var d=w.diagnostic("a");assertFalse(d.get("packet_applied").getAsBoolean());
        assertEquals(20,d.get("prediction_clear_tick").getAsLong());assertEquals(20,d.get("stable_since").getAsLong());
    }
    @Test void unappliedCorrectionFailsImmediatelyAndCannotBeWashedByLaterExpectedPacket(){
        var w=window();assertFalse(w.packet("a","Block{minecraft:air}",true,false,10));
        assertEquals("SERVER_PACKET_CORRECTION",w.failureReason());
        var frozen=w.diagnostic("a").deepCopy();assertFalse(w.packet("a",BLOCK,true,true,11));
        assertFalse(w.observeProof(49,48,observation(false,true,true),30));
        assertEquals(frozen,w.diagnostic("a"));assertEquals(0,w.settled());
    }
    @Test void predictedExpectedStateAndConsumptionWithoutPacketTimesOut(){
        var w=window();assertTrue(w.observeProof(49,48,observation(false,true,true),99));
        assertEquals(0,w.settled());assertFalse(w.observeProof(49,48,observation(false,true,true),100));
        assertEquals("NO_SERVER_PACKET_TIMEOUT",w.failureReason());
        assertFalse(w.packet("a",BLOCK,true,true,101));assertFalse(w.canSend());
    }
    @Test void packetAtNinetyTwoAndNinetyNineKeepsItsFullEightTicks(){
        for(int packet:new int[]{92,99}){
            var w=window();assertTrue(w.observeProof(49,48,observation(false,true,true),packet-1));
            assertTrue(w.packet("a",BLOCK,true,false,packet));
            assertTrue(w.observeProof(49,48,observation(false,true,true),packet));
            assertTrue(w.observeProof(49,48,observation(false,true,true),packet+7));assertEquals(0,w.settled());
            assertTrue(w.observeProof(49,48,observation(false,true,true),packet+8));assertEquals(1,w.settled());
        }
    }
    @Test void unknownPredictionQueryWaitsBoundedlyWithoutCredit(){
        var w=window();assertTrue(w.packet("a",BLOCK,true,false,10));
        assertTrue(w.observeProof(49,48,observation(null,true,true),109));assertEquals(0,w.settled());
        assertFalse(w.observeProof(49,48,observation(null,true,true),110));
        assertEquals("PREDICTION_QUERY_UNAVAILABLE",w.failureReason());
        assertTrue(w.diagnostic("a").get("prediction_pending").isJsonNull());
    }
    @Test void neverClearingPredictionHasASeparateFiniteLimit(){
        var w=window();assertTrue(w.packet("a",BLOCK,true,false,99));
        assertTrue(w.observeProof(49,48,observation(true,false,true),198));assertEquals(0,w.settled());
        assertFalse(w.observeProof(49,48,observation(true,false,true),199));
        assertEquals("PREDICTION_UNRESOLVED_TIMEOUT",w.failureReason());
    }
    @Test void inventorySynchronizationAfterPacketAndPredictionGetsItsOwnEightTicks(){
        var w=window();assertTrue(w.packet("a",BLOCK,true,false,99));
        assertTrue(w.observeProof(49,49,observation(false,true,true),99));
        assertTrue(w.observeProof(49,48,observation(false,true,true),120));
        assertTrue(w.observeProof(49,48,observation(false,true,true),127));assertEquals(0,w.settled());
        assertTrue(w.observeProof(49,48,observation(false,true,true),128));assertEquals(1,w.settled());
        assertEquals(120,w.diagnostic("a").get("stable_since").getAsLong());
    }
    @Test void receivedPacketDoesNotPermitUnboundedInventoryWaiting(){
        var w=window();assertTrue(w.packet("a",BLOCK,true,false,99));
        assertTrue(w.observeProof(49,49,observation(false,true,true),239));
        assertFalse(w.observeProof(49,49,observation(false,true,true),240));
        assertEquals("ATTEMPT_TIMEOUT",w.failureReason());
    }
    @Test void foreignPreSendUnknownTargetAndClosedPacketsHaveNoAuthority(){
        var w=window();assertFalse(w.packet("a",BLOCK,false,false,1));
        assertFalse(w.packet("a",BLOCK,true,false,-1));assertFalse(w.packet("other",BLOCK,true,false,1));
        assertEquals(-1,w.diagnostic("a").get("packet_tick").getAsLong());
        assertTrue(w.packet("a",BLOCK,true,false,2));
        assertTrue(w.observeProof(49,48,observation(false,true,true),2));
        w.close();var frozen=w.diagnostic("a").deepCopy();
        assertFalse(w.packet("a","wrong",true,true,3));
        assertFalse(w.observeProof(49,48,observation(false,true,true),10));
        assertEquals(frozen,w.diagnostic("a"));assertEquals(0,w.settled());
    }
    @Test void excessConsumptionAndSettledInventoryRollbackFailClosed(){
        var excess=window();excess.packet("a",BLOCK,true,false,1);
        assertFalse(excess.observeProof(49,47,observation(false,true,true),1));
        assertEquals("CUMULATIVE_INVENTORY_DIVERGED",excess.failureReason());
        var rollback=window();rollback.packet("a",BLOCK,true,false,1);
        assertTrue(rollback.observeProof(49,48,observation(false,true,true),1));
        assertTrue(rollback.observeProof(49,48,observation(false,true,true),9));assertEquals(1,rollback.settled());
        assertFalse(rollback.observeProof(49,49,observation(false,true,true),10));assertFalse(rollback.canSend());
    }
    @Test void serverChunkLossAndPredictionClearWorldMismatchReject(){
        var unloaded=window();unloaded.packet("a",BLOCK,true,false,1);
        assertFalse(unloaded.observeProof(49,48,observation(true,false,false),1));
        assertEquals("SERVER_CHUNK_NOT_CURRENT",unloaded.failureReason());
        var mismatch=window();mismatch.packet("a",BLOCK,true,false,1);
        assertTrue(mismatch.observeProof(49,48,observation(true,false,true),1));
        assertFalse(mismatch.observeProof(49,48,observation(false,false,true),2));
        assertEquals("WORLD_STATE_DIVERGED",mismatch.failureReason());
    }
    @Test void predictionReopensAndInventoryRollsWithinWindowRestartsStability(){
        var w=window();w.packet("a",BLOCK,true,false,1);
        assertTrue(w.observeProof(49,48,observation(false,true,true),1));
        assertTrue(w.observeProof(49,48,observation(true,true,true),7));assertEquals(0,w.settled());
        assertTrue(w.observeProof(49,48,observation(false,true,true),8));
        assertTrue(w.observeProof(49,48,observation(false,true,true),15));assertEquals(0,w.settled());
        assertTrue(w.observeProof(49,48,observation(false,true,true),16));assertEquals(1,w.settled());
    }
    @Test void callbackRetainsUnappliedPacketsAndPollingOnlyReadsPrediction()throws Exception{
        var source=Files.readString(Path.of("src/client/java/dev/twob2tkit/automation/ProjectionScaffoldFill.java"));
        int begin=source.indexOf("void serverBlock(");int end=source.indexOf("Outcome observe(",begin);
        String callback=source.substring(begin,end);
        assertFalse(callback.contains("!applied"));assertTrue(callback.contains("true,applied,tick"));
        assertTrue(callback.contains("tick<attempt.sentTick"));assertTrue(callback.contains("c.getConnection()!=connection"));
        assertTrue(source.contains("predictions.pending(c.level,attempt.pos)"));
        assertFalse(source.contains("startObservedBreak"));assertFalse(source.contains("syncSelected"));
        assertTrue(source.contains("ackWindow.close()"));assertTrue(source.contains("failure_reason"));
        assertTrue(source.contains("stable_since"));assertTrue(source.contains("prediction_clear_tick"));
    }
}
