package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class SingleBlockBridgeConfirmationTest {
    private MethodNode method(String name)throws Exception {
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method) {
        var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode call)result.add(call.name);return result;
    }
    private List<String> constants(MethodNode method) {
        var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof LdcInsnNode value&&value.cst instanceof String text)result.add(text);return result;
    }
    @Test void inputHoldsPredictedOrCorrectedRemovalBeforeFootingChecksAndUsesNativeProofWrapper()throws Exception {
        var names=calls(method("beforeInput"));assertTrue(names.containsAll(List.of("singleBlockConfirmed","hold","mine")));
        assertTrue(names.indexOf("singleBlockConfirmed")<names.indexOf("stableFloor"));
        assertTrue(names.indexOf("hold")<names.indexOf("mine"));
        assertFalse(constants(method("beforeInput")).contains("target removed"));
    }
    @Test void dispatchRegistersProofAfterStoppingEarlierWorkAndBeforeAssigningTheMiningOperation()throws Exception {
        var names=calls(method("dispatch"));assertTrue(names.contains("begin"));
        var node=method("dispatch");int offset=0,mineRegistration=-1,lastStop=-1;
        for(var i:node.instructions){
            if(i instanceof MethodInsnNode call){
                if(call.name.equals("stopWork"))lastStop=offset;
                if(call.owner.equals("dev/twob2tkit/automation/SingleBlockMiningConfirmation")&&call.name.equals("begin")){mineRegistration=offset;break;}
            }
            offset++;
        }
        assertTrue(lastStop>=0&&mineRegistration>lastStop);
    }
    @Test void tickNeverCompletesOrdinaryMiningFromAirAndPrinterDeadlineIsWaiting()throws Exception {
        var values=constants(method("tick"));assertFalse(values.contains("target removed"));
        var timeout="printer interval ended without complete current bounded-mask server confirmation";
        int index=values.indexOf(timeout);assertTrue(index>0);assertEquals("waiting",values.get(index-1));
        assertTrue(calls(method("tick")).contains("singleBlockConfirmed"));
        assertTrue(values.contains("single target confirmation timed out; outcome pending, no second excavation sent"));
    }
    @Test void finishRevalidatesBothScopesBeforeReleasingNativeStateAndCancelKeepsClaims()throws Exception {
        var names=calls(method("finish"));assertTrue(names.containsAll(List.of("singleBlockConfirmed","boundedPrinterComplete","singleBlockConfirmation","printerConfirmation","close")));
        assertTrue(names.indexOf("singleBlockConfirmed")<names.indexOf("singleBlockConfirmation"));
        assertTrue(names.indexOf("boundedPrinterComplete")<names.indexOf("printerConfirmation"));
        assertTrue(names.indexOf("singleBlockConfirmation")<names.indexOf("stop"));
        assertTrue(calls(method("cancelWork")).containsAll(List.of("singleBlockConfirmation","close","saveTerminalConfirmation")));
    }
    @Test void exactMiningReceiptCarriesOnlyObservedPacketAndSequenceEvidence()throws Exception {
        var values=constants(method("singleBlockConfirmation"));
        assertTrue(values.containsAll(List.of("server_confirmed","confirmation_scope","server_update_seen","server_observed_state","native_sequence","server_ack_sequence","outcome_pending")));
        var names=calls(method("singleBlockConfirmation"));assertTrue(names.containsAll(List.of("sentSequence","ackSequence","serverUpdateSeen","serverState")));
        assertTrue(calls(method("nativeMaterialReceipt")).contains("attachTerminalConfirmation"));
    }
    @Test void printerReceiptExplicitlyLimitsCompletionToItsCapturedMask()throws Exception {
        var request=new JsonObject();request.addProperty("id","printer-a");request.addProperty("printer_completion_world","world");
        request.addProperty("printer_completion_key","projection-a");
        request.add("printer_completion_targets",com.google.gson.JsonParser.parseString("[[1,2,3],[4,5,6]]"));
        var method=AutomationBridge.class.getDeclaredMethod("printerConfirmation",JsonObject.class,String.class,String.class,boolean.class);method.setAccessible(true);
        var done=(JsonObject)method.invoke(null,request,"done","bounded mask confirmed",true);
        assertTrue(done.get("server_confirmed").getAsBoolean());assertFalse(done.get("full_projection_confirmed").getAsBoolean());
        assertEquals(2,done.get("bounded_target_count").getAsInt());assertEquals("projection-a",done.get("placement_key").getAsString());
        assertEquals("current_bounded_mask_distinct_exact_final_server_updates",done.get("confirmation_scope").getAsString());
        var waiting=(JsonObject)method.invoke(null,request,"waiting","time limit",false);
        assertFalse(waiting.get("server_confirmed").getAsBoolean());assertTrue(waiting.get("outcome_pending").getAsBoolean());
        assertEquals("none",waiting.get("confirmation_scope").getAsString());
    }
}
