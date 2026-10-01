package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

/** Verify that the two material entry points hold the same narrow mining isolation. */
class MaterialMiningLeaseWiringTest {
    private MethodNode method(String owner,String name)throws Exception{
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+owner+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode node){
        var result=new ArrayList<String>();
        for(var instruction:node.instructions)if(instruction instanceof MethodInsnNode call)result.add(call.name);
        return result;
    }
    @Test void nativeAndExternalAcquisitionShareInstalledModuleIsolation()throws Exception{
        var nativeOpen=calls(method("automation/AutomationBridge","nativeMaterialOpen"));
        assertTrue(nativeOpen.contains("acquireMaterialMiningLease"));
        assertTrue(nativeOpen.indexOf("armPveGuard")<nativeOpen.indexOf("acquireMaterialMiningLease"));
        assertTrue(calls(method("automation/NativeMaterialSession","open")).contains("nativeMaterialOpen"));
        var external=calls(method("automation/AutomationBridge","dispatch"));
        assertTrue(external.contains("acquireMaterialMiningLease"));
        var acquire=calls(method("automation/AutomationBridge","acquireMaterialMiningLease"));
        assertTrue(acquire.containsAll(List.of("materialMiningScope","acquire","close")));
    }
    @Test void leaseObservationPrecedesNativeAndExternalActions()throws Exception{
        var tick=calls(method("automation/AutomationBridge","tick"));
        assertEquals("syncMaterialMiningLease",tick.getFirst());
        assertTrue(tick.indexOf("syncMaterialMiningLease")<tick.indexOf("nativeMaterialRunQueued"));
        assertTrue(tick.indexOf("syncMaterialMiningLease")<tick.indexOf("dispatch"));
        assertEquals("syncMaterialMiningLease",calls(method("automation/AutomationBridge","beforeInput")).getFirst());
        assertEquals("syncMaterialMiningLease",calls(method("automation/AutomationBridge","nativeMaterialCheck")).getFirst());
    }
    @Test void externalToggleRoundTripRevokesScopeAndAdvancesExistingControlRevision()throws Exception{
        assertTrue(calls(method("mixin/MeteorScaffoldModuleLifecycleMixin","kit$observeLeasedModuleToggle"))
            .contains("moduleToggleObserved"));
        var sync=method("automation/AutomationBridge","syncMaterialMiningLease");
        assertTrue(calls(sync).containsAll(List.of("ready","stopWork","releaseMaterialMiningLease")));
        boolean cleared=false,revision=false;
        for(var instruction:sync.instructions)if(instruction instanceof FieldInsnNode field)
            if(field.name.equals("supervisionLease")&&field.getOpcode()==Opcodes.PUTSTATIC)cleared=true;
        for(var instruction:method("automation/AutomationBridge","cancelWork").instructions)
            if(instruction instanceof FieldInsnNode field&&field.name.equals("controlRevision")
                    &&field.getOpcode()==Opcodes.PUTSTATIC)revision=true;
        assertTrue(cleared&&revision);
    }
    @Test void disconnectCancelParkingAndExternalReleaseCloseIsolation()throws Exception{
        for(String name:List.of("disconnected","afterDisconnectCleanup","cancel","cancelWork","retainParkingLease"))
            assertTrue(calls(method("automation/AutomationBridge",name)).contains("releaseMaterialMiningLease"),name);
        assertTrue(calls(method("automation/AutomationBridge","nativeMaterialFinish")).contains("releaseMaterialMiningLease"));
        assertTrue(calls(method("automation/AutomationBridge","dispatch")).contains("releaseMaterialMiningLease"));
    }
    @Test void queuedMeteorPacketsAreConditionalAndKitMiningRemainsTheExistingPrimitive()throws Exception{
        var hook=method("mixin/MeteorInstantRebreakMaterialMixin","kit$keepMaterialMiningOwned");
        var invocations=calls(hook);
        assertEquals(List.of("materialMiningPacketBlocked","cancel"),invocations);
        assertTrue(java.util.stream.StreamSupport.stream(hook.instructions.spliterator(),false)
            .anyMatch(i->i instanceof JumpInsnNode jump&&jump.getOpcode()==Opcodes.IFEQ),
            "No current material lease must leave InstantRebreak behavior untouched");
        assertTrue(calls(method("automation/AutomationBridge","materialMiningPacketBlocked"))
            .containsAll(List.of("materialMiningScope","packetBlocked")));
        assertTrue(calls(method("automation/AutomationBridge","beforeInput"))
            .containsAll(List.of("startDestroyBlock","continueDestroyBlock")));
        var snapshots=method("automation/AutomationBridge","snapshot");
        assertTrue(calls(snapshots).contains("snapshot"));
        assertTrue(java.util.stream.StreamSupport.stream(snapshots.instructions.spliterator(),false)
            .anyMatch(i->i instanceof LdcInsnNode constant&&"material_mining_isolation".equals(constant.cst)));
        var injection=hook.visibleAnnotations.stream().filter(a->a.desc.endsWith("/Inject;")).findFirst().orElseThrow();
        assertTrue(injection.values.contains("sendPacket()V")||injection.values.stream()
            .anyMatch(value->value instanceof List<?> list&&list.contains("sendPacket()V")));
    }
}
