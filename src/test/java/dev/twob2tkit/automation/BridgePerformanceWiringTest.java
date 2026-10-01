package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class BridgePerformanceWiringTest {
    private MethodNode method(String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method){
        var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode call)result.add(call.name);return result;
    }
    private List<String> constants(MethodNode method){
        var result=new ArrayList<String>();for(var i:method.instructions)if(i instanceof LdcInsnNode value&&value.cst instanceof String text)result.add(text);return result;
    }
    @Test void entitySnapshotsAndScanSupplementUseSpatialQueriesInsteadOfWholeRenderingLists()throws Exception{
        for(String name:List.of("snapshot","scanEntities")){
            var names=calls(method(name));assertTrue(names.contains("getEntities"));assertFalse(names.contains("entitiesForRendering"));
        }
        assertTrue(calls(method("snapshot")).contains("distanceToSqr"));
    }
    @Test void scanScopeAndManualControlAreCheckedBeforeItsOnlyClientThreadBudgetRead()throws Exception{
        var names=calls(method("tickScan"));assertTrue(names.containsAll(List.of("session","manualMovementDown","advance")));
        assertTrue(names.indexOf("session")<names.indexOf("advance"));assertTrue(names.indexOf("manualMovementDown")<names.indexOf("advance"));
        assertTrue(calls(method("tick")).indexOf("tickScan")<calls(method("tick")).indexOf("tickInterfacePause"));
    }
    @Test void scanLifecycleDoesNotTakeOverTheActiveWorkAndExactReplyBypassesStatusCoalescing()throws Exception{
        for(String name:List.of("startScan","tickScan","finishScan","publishScan"))for(var i:method(name).instructions)
            if(i instanceof FieldInsnNode field&&field.getOpcode()==Opcodes.PUTSTATIC)
                assertFalse(List.of("active","op","phase","deadline").contains(field.name),name+" must leave current work intact");
        assertTrue(calls(method("publishScan")).containsAll(List.of("submit","retry","release")));
        assertFalse(calls(method("publishScan")).contains("save"));
        for(var i:method("publishScan").instructions)if(i instanceof MethodInsnNode call&&call.name.equals("submit"))
            assertEquals("dev/twob2tkit/automation/ExactScanReplyWriter",call.owner);
        assertTrue(calls(method("nativeMaterialPoll")).contains("equals"));
    }
    @Test void multiTickRepliesExposeSamplingWindowAndPartialFailureRows()throws Exception{
        var values=constants(method("finishScan"));assertTrue(values.containsAll(List.of("scan_coherent","scan_started_at","scan_ended_at","scan_elapsed_ticks","scan_cells_read","scan_start_revision","scan_end_revision","blocks")));
        assertTrue(values.contains("scan_snapshot_failure"));
        assertTrue(constants(method("publishScan")).contains("[Scan] exact reply IO failed type={}; sampled records retained for retry"));
    }
    @Test void heartbeatIOUsesTheCacheAndKeepsTheFifteenSecondAndLiveSafetyChecks()throws Exception{
        var names=calls(method("tickSupervision"));assertTrue(names.contains("read"));
        assertFalse(names.contains("readString"));assertTrue(names.containsAll(List.of("manualMovementDown","getHealth","decide")));
        boolean ttl=false;for(var i:method("tickSupervision").instructions)if(i instanceof LdcInsnNode value&&value.cst instanceof Long n&&n==15000L)ttl=true;
        assertTrue(ttl);
    }
    @Test void snapshotCachesSlotSerializationInsideTheCurrentMenuAndWorldScope()throws Exception{
        var names=calls(method("snapshot"));assertTrue(names.containsAll(List.of("begin","snapshotStack","getCarried","session")));
        assertTrue(names.indexOf("begin")<names.indexOf("snapshotStack"));
        assertTrue(calls(method("snapshotStack")).contains("cached"));
        assertTrue(calls(method("stack")).contains("addItemDetails"));
    }
    @Test void onlyStatusWritesAreOffThreadAndHudRemainsBeforeEnqueue()throws Exception{
        var names=calls(method("writeStatus"));assertTrue(names.containsAll(List.of("update","submit")));
        assertTrue(names.indexOf("update")<names.indexOf("submit"));assertFalse(names.contains("save"));
        assertTrue(calls(method("saveTerminalConfirmation")).contains("save"));
    }
}
