package dev.twob2tkit.automation;

import java.util.*;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class IdleActivityWiringTest {
    ClassNode code(String type)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+type+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);}return node;
    }
    MethodNode method(ClassNode type,String name){return type.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    Set<String> calls(MethodNode method){var result=new HashSet<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode call)result.add(call.name);return result;}
    Set<String> strings(MethodNode method){var result=new HashSet<String>();for(var i:method.instructions)if(i instanceof LdcInsnNode literal&&literal.cst instanceof String s)result.add(s);return result;}
    @Test void readOnlySnapshotPublishesTheLiveAggregateWithoutStoppingOrWritingOwner()throws Exception{
        var bridge=code("automation/AutomationBridge");var snapshot=method(bridge,"snapshot");
        assertTrue(strings(snapshot).containsAll(Set.of("idle_activity_protocol","idle_activity")));
        assertTrue(calls(snapshot).contains("idleActivitySnapshot"));
        var aggregate=method(bridge,"idleActivitySnapshot");assertTrue(calls(aggregate).containsAll(Set.of("idleOwner","idleActivities","conflicts")));
        assertFalse(calls(aggregate).contains("preemptIdleForPlayer"));assertFalse(calls(aggregate).contains("stopWork"));
        assertTrue(calls(method(bridge,"idleFisherOwned")).contains("activityGeneration"));
        assertFalse(calls(method(bridge,"materialJobContext")).contains("preemptIdleForPlayer"));
    }
    @Test void actualHiddenModulesAndEveryLeasedPrimitiveFeedActivity()throws Exception{
        var kit=method(code("KitClient"),"idleActivities");
        assertTrue(strings(kit).containsAll(Set.of("nether_roof","navigation","fisher","borer","surround","planter","feeder","chopper",
            "machine_printer","projection_build","concrete","structure_guide","material_task","caretaker_task","container_restock","area_pick","navigation_logout","guard_view","brawler_view")));
        assertTrue(calls(kit).containsAll(Set.of("isActive","isPlacing","snapshot","occupied")));
        var nativeFlags=method(code("automation/AutomationBridge"),"idleActivities");
        assertTrue(strings(nativeFlags).containsAll(Set.of("native_request","native_material_owner","material_lease","scan","bucket","map","air_seed","craft","supply","scaffold_row","air_navigation","professional_printer","meteor_scaffold","guard")));
    }
    @Test void scopedPreemptionChecksAuthorityStopsRealInputsAndReleasesWithoutDisarmingOrLogout()throws Exception{
        var bridge=code("automation/AutomationBridge");var preempt=method(bridge,"preemptIdle");
        assertTrue(calls(preempt).containsAll(Set.of("idleOwnerForAction","mayCancel","stopWork","inputsReleased","releaseMaterialMiningLease","restorePhysicalMovement")));
        assertFalse(calls(preempt).contains("safeLogout"));assertFalse(calls(preempt).contains("disarmGuard"));
        assertFalse(calls(preempt).contains("save"));assertTrue(strings(preempt).containsAll(Set.of("revision_before","revision_after","input_released","yield_ack"))||strings(preempt).contains("input_released"));
        assertTrue(calls(method(bridge,"dispatch")).contains("preemptIdle"));
        var scoped=code("KitClient").methods.stream().filter(m->m.name.equals("stopWork")&&m.desc.contains("java/util/Set")).findFirst().orElseThrow();
        assertTrue(calls(scoped).contains("stopKeepingMenu"));assertTrue(calls(scoped).contains("cancelWork"));
    }
    @Test void manualYieldRunsBeforePublishingAndBlocksOldLookReapplication()throws Exception{
        var bridge=code("automation/AutomationBridge");
        assertTrue(calls(method(bridge,"writeStatus")).contains("preemptIdleForManual"));
        assertTrue(calls(method(bridge,"yieldGuardToManualInput")).contains("idleManualHolding"));
        var kit=code("KitClient");assertTrue(calls(method(kit,"tickNavigation")).contains("preemptIdleForManual"));
        assertTrue(calls(method(kit,"reapplyNavigationRotation")).contains("idleManualHolding"));
    }
    @Test void formalStartsExplicitlyPreemptWhileProbeAndContextStayReadOnly()throws Exception{
        var jobs=code("material/MaterialJobs");
        assertTrue(calls(method(jobs,"start")).contains("preemptIdleForPlayer"));assertTrue(calls(method(jobs,"resume")).contains("preemptIdleForPlayer"));
        var care=code("material/CaretakerJobs");assertTrue(calls(method(care,"prepare")).contains("preemptIdleForPlayer"));
        for(var m:care.methods)if(m.name.toLowerCase().contains("probe"))assertFalse(calls(m).contains("preemptIdleForPlayer"));
        var kit=code("KitClient");for(String name:List.of("startFisher","startPlanter","startChopper","startFeeder","startNetherRoof"))
            assertTrue(calls(method(kit,name)).contains("preemptIdleForPlayer"),name);
        assertTrue(calls(method(code("automation/AutomationBridge"),"userTaskStarting")).contains("preemptIdleForPlayer"));
        for(String name:List.of("prepareForCruise","prepareForMachine","prepareForBorer","toggleProjectionBuild"))
            assertTrue(calls(method(kit,name)).contains("userTaskStarting"),name);
    }
    @Test void fisherKeepingMenuStopsTickAndChestNavigationWithoutContainerMutation()throws Exception{
        var fisher=code("fisher/AutoFisher");var keeping=method(fisher,"stopKeepingMenu");
        assertTrue(fisher.methods.stream().filter(m->m.name.equals("start")).anyMatch(m->
            java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false)
                .anyMatch(i->i instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTFIELD&&f.name.equals("activityGeneration"))));
        assertFalse(calls(keeping).contains("closeContainer"));assertTrue(calls(keeping).contains("stop"));
        var body=fisher.methods.stream().filter(m->m.name.equals("stop")&&m.desc.endsWith("Z)V")).findFirst().orElseThrow();
        var writes=new HashSet<String>();boolean keepMenuGuard=false,rodGuard=false;
        for(var instruction:body.instructions){
            if(instruction instanceof FieldInsnNode field&&field.getOpcode()==Opcodes.PUTFIELD)writes.add(field.name);
            if(instruction instanceof VarInsnNode local&&local.getOpcode()==Opcodes.ILOAD&&local.var==3)keepMenuGuard=true;
            if(instruction instanceof TypeInsnNode type&&type.desc.endsWith("FishingRodItem"))rodGuard=true;
        }
        assertTrue(writes.containsAll(Set.of("active","phase","chestPos","cooldown","openWait","caughtWait","sawBite")));
        assertTrue(keepMenuGuard);assertTrue(rodGuard);
        assertFalse(calls(body).contains("handleContainerInput"));
        var supply=code("automation/BuildSupplyTask");
        assertTrue(calls(method(supply,"closeKeepingMenu")).contains("close"));
        assertFalse(calls(method(supply,"closeKeepingMenu")).contains("closeContainer"));
        assertTrue(calls(method(code("automation/AutomationBridge"),"cancelWork")).contains("closeForIdleHandoff"));
    }
    @Test void idleFishingModeAndEntityEvidenceAreRealHostPaths()throws Exception{
        var fisher=code("fisher/AutoFisher");assertTrue(calls(method(fisher,"startIdleNoDeposit")).contains("start"));
        var tick=method(fisher,"tick");var ordered=new ArrayList<String>();for(var i:tick.instructions)if(i instanceof MethodInsnNode c)ordered.add(c.name);
        assertTrue(ordered.indexOf("decide")>=0&&ordered.indexOf("decide")<ordered.indexOf("handleStash"));
        assertTrue(calls(tick).contains("stopKeepingMenu"));
        var bridge=code("automation/AutomationBridge");assertTrue(calls(method(bridge,"dispatch")).contains("startIdleFisher"));
        assertTrue(strings(method(bridge,"snapshot")).containsAll(Set.of("idle_fishing_protocol","fisher_chest_range","fisher_deposit_allowed")));
        assertTrue(strings(method(bridge,"scanEntities")).containsAll(Set.of("hostile","bounds","min","max")));
        assertTrue(calls(method(bridge,"scanEntities")).contains("getBoundingBox"));
    }
}
