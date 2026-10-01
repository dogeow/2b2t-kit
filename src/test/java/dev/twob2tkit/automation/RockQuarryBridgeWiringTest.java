package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RockQuarryBridgeWiringTest {
    private MethodNode method(String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);}
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(String name)throws Exception{
        var result=new ArrayList<String>();for(var instruction:method(name).instructions)
            if(instruction instanceof MethodInsnNode call)result.add(call.name);return result;
    }
    private Set<String> text(String name)throws Exception{
        var result=new HashSet<String>();for(var instruction:method(name).instructions)
            if(instruction instanceof LdcInsnNode constant&&constant.cst instanceof String value)result.add(value);return result;
    }
    @Test void safetyAndObservedBoundsPrecedeBorrowingTheNativeArea()throws Exception{
        var sequence=calls("startRockQuarry");
        assertTrue(sequence.indexOf("rockScope")<sequence.indexOf("startMaterialArea"));
        assertTrue(sequence.indexOf("inspectRockQuarry")<sequence.indexOf("startMaterialArea"));
        assertTrue(sequence.indexOf("toolAllowed")<sequence.indexOf("startMaterialArea"));
        assertFalse(sequence.contains("save"),"The batch must not replace the player's saved A/B settings");
    }
    @Test void nextMiningInputRechecksBufferAndStoppingAlwaysStopsItsBorer()throws Exception{
        assertTrue(calls("beforeInput").contains("tickRockQuarry"));
        assertTrue(calls("tickRockQuarry").containsAll(List.of("inspectRockQuarry","rockScope","result","begin")));
        for(String method:List.of("finish","cancelWork")){
            assertTrue(text(method).contains("rock_quarry_batch"));assertTrue(calls(method).contains("stop"));
        }
        assertTrue(text("dispatch").containsAll(Set.of("quarry_batch","rock_quarry_batch")));
    }
    @Test void receiptSeparatesRetainedLightsAndInventoryGainAndSupportsBothEntryPoints()throws Exception{
        assertTrue(text("snapshot").containsAll(Set.of("rock_quarry_protocol","raw_iron_block_quarry_protocol","rock_quarry")));
        assertTrue(text("updateRockQuarry").containsAll(Set.of("gained","current","remaining_blocks","retained_lights","pending_blocks","area_cleared")));
        assertTrue(text("nativeMaterialSubmit").contains("rock_quarry_batch"));
        assertTrue(calls("materialJobCancel").indexOf("ownsCancel")<calls("materialJobCancel").indexOf("stopWork"));
        assertFalse(calls("materialJobCancel").contains("disarmGuard"));
        assertFalse(calls("materialJobCancel").contains("joined"));
    }
    @Test void flightExceptionUsesCurrentRequestLeaseAndExactBorrowedAreaWithoutWeakeningOtherSafety()throws Exception{
        var gate=calls("rockFlightAllowed");assertTrue(gate.containsAll(List.of("currentMaterialRequest","rockBounds","ownsMaterialArea","flightAllowed")));
        assertTrue(text("rockFlightAllowed").contains("rock_quarry_batch"));
        boolean exactRequest=false;for(var instruction:method("rockFlightAllowed").instructions)
            if(instruction instanceof JumpInsnNode jump&&jump.getOpcode()==org.objectweb.asm.Opcodes.IF_ACMPNE)exactRequest=true;
        assertTrue(exactRequest,"A copied/foreign request cannot claim the active excavation");
        var safety=calls("rockScope");assertTrue(safety.containsAll(List.of("held","guardArmed","pveOnly","healthy","manualMovementDown","nativeKitMenu","rockFlightAllowed","silk")));
        assertTrue(text("rockScope").containsAll(Set.of("materials","task_session","job_session","world_session","revision")));
        var fields=new HashSet<String>();for(var instruction:method("rockScope").instructions)
            if(instruction instanceof FieldInsnNode field)fields.add(field.name);
        assertTrue(fields.containsAll(Set.of("borerAutoDefend","SURVIVAL","OVERWORLD")));
        assertTrue(text("rockScope").contains(dev.twob2tkit.MeteorModules.AUTO_LOG));
    }

}
