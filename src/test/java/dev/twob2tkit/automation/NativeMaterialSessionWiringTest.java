package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

/** The local UI adapter must keep ownership through each existing native child. */
class NativeMaterialSessionWiringTest {
    private MethodNode method(String owner,String name)throws Exception{
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+owner+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method){
        var result=new ArrayList<String>();
        for(var instruction:method.instructions)
            if(instruction instanceof MethodInsnNode invoke)result.add(invoke.name);
        return result;
    }
    @Test void submitQueuesAndOnlyBridgeTickDispatches(){
        try{
            assertFalse(calls(method("automation/AutomationBridge","nativeMaterialSubmit")).contains("dispatch"));
            assertTrue(calls(method("automation/AutomationBridge","nativeMaterialRunQueued")).contains("dispatch"));
            assertTrue(calls(method("automation/AutomationBridge","tick")).contains("nativeMaterialRunQueued"));
        }catch(Exception e){throw new AssertionError(e);}
    }
    @Test void ownedInterruptRetainsLeaseAndSafeLogoutDisablesReconnectFirst()throws Exception{
        var interrupt=calls(method("automation/AutomationBridge","nativeMaterialInterrupt"));
        assertTrue(interrupt.containsAll(List.of("nativeMaterialCheck","stopWork","nativeMaterialReceipt")));
        var logout=calls(method("automation/AutomationBridge","nativeMaterialSafeLogout"));
        assertTrue(logout.indexOf("nativeMaterialCheck")<logout.indexOf("suspendAutoReconnect"));
        assertTrue(logout.indexOf("suspendAutoReconnect")<logout.indexOf("safeLogout"));
        var finish=method("automation/AutomationBridge","nativeMaterialFinish");
        var finishCalls=calls(finish);
        assertTrue(finishCalls.contains("highGuardPark"));
        assertTrue(finishCalls.indexOf("stopWork")<finishCalls.indexOf("armPveGuard"));
        var writes=new ArrayList<String>();
        for(var instruction:finish.instructions)
            if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
                    &&field.getOpcode()==org.objectweb.asm.Opcodes.PUTSTATIC)writes.add(field.name);
        assertTrue(writes.contains("nativeMaterialDispatch"),"Finish must not re-enter the collector stop hook");
    }
    @Test void publicAdapterExposesOwnedLifecycle()throws Exception{
        var methods=NativeMaterialSession.class.getMethods();
        var names=new java.util.HashSet<String>();for(var method:methods)names.add(method.getName());
        assertTrue(names.containsAll(List.of("open","submit","poll","snapshot","busy",
            "interrupt","finish","cancel","safeLogout")));
        assertTrue(calls(method("automation/AutomationBridge","nativeMaterialCheck"))
            .containsAll(List.of("session","manualMovementDown","guardArmed")));
    }

    @Test void waterPreflightAcceptsFlowingWaterAndChecksFlowingLava()throws Exception{
        var fields=new ArrayList<String>();
        for(var instruction:method("automation/AutomationBridge","dispatch").instructions)
            if(instruction instanceof org.objectweb.asm.tree.FieldInsnNode field
                    &&field.owner.equals("net/minecraft/tags/FluidTags"))fields.add(field.name);
        assertTrue(fields.contains("WATER"));
        assertTrue(fields.contains("LAVA"));
    }
    @Test void gravelLocalApiUsesCollectorAndChecksWorldScope()throws Exception{
        var dispatch=calls(method("automation/AutomationBridge","dispatch"));
        assertTrue(dispatch.containsAll(List.of("gravelScope","configureGravel","start","stop")));
        assertTrue(calls(method("automation/AutomationBridge","gravelScope")).contains("session"));
    }
}
