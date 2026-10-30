package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectedSourceColumnWiringTest {
    List<String> calls(String cls,String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var m=node.methods.stream().filter(v->v.name.equals(name)).findFirst().orElseThrow();var result=new ArrayList<String>();
        for(var instruction:m.instructions)if(instruction instanceof MethodInsnNode c)result.add(c.owner+"."+c.name);return result;
    }
    @Test void nativeBucketPathRetainsExclusiveAdmissionNormalUseAndDurableClaim()throws Exception{
        var constructor=calls("BucketWaterAction","<init>");
        assertTrue(constructor.contains("dev/twob2tkit/automation/ProjectedSourceColumnPolicy.exclusivePlace"));
        assertTrue(constructor.contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.<init>"));
        assertTrue(calls("BucketWaterAction","boundedHole").contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.require"));
        var use=calls("BucketWaterAction","useOnce");
        assertTrue(use.indexOf("dev/twob2tkit/automation/BucketWaterAction.validateBeforeSend")<use.indexOf("dev/twob2tkit/automation/BucketUseStore.claim"));
        assertTrue(use.stream().anyMatch(v->v.endsWith(".useItem")));assertFalse(use.stream().anyMatch(v->v.endsWith(".setBlock")));
    }
    @Test void runningHostAdvertisesTheNewProtocolToPreventSilentOldModeFallback()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        for(String protocol:List.of("projected_source_column_protocol","projected_source_column_shielded_work_protocol","projected_source_column_supply_protocol"))
            assertTrue(node.methods.stream().filter(m->m.name.equals("snapshot")).anyMatch(m->{
                for(var instruction:m.instructions)if(instruction instanceof LdcInsnNode ldc&&protocol.equals(ldc.cst))return true;
                return false;
            }));
    }
    @Test void shieldedEligibilityKeepsTheOrdinaryHostileCheckAndRevalidatesTheSourceGuard()throws Exception{
        var owner=calls("AutomationBridge","bucketOwnerCurrent");
        assertTrue(owner.contains("dev/twob2tkit/automation/AutomationBridge.loadedHostileNearby"));
        assertTrue(owner.contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.shieldedWorkspace"));
        var shield=calls("ProjectedSourceColumnGuard","shieldedWorkspace");
        assertTrue(shield.contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.require"));
        assertTrue(shield.contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.shieldedActor"));
        var actor=calls("ProjectedSourceColumnGuard","shieldedActor");
        assertTrue(actor.contains("dev/twob2tkit/automation/SourceColumnThreatPolicy.permit"));
        assertTrue(actor.contains("dev/twob2tkit/automation/SourceColumnThreatPolicy.remoteCreeper"));
        assertTrue(shield.indexOf("dev/twob2tkit/automation/ProjectedSourceColumnGuard.require")<shield.indexOf("dev/twob2tkit/automation/ProjectedSourceColumnGuard.shieldedActor"));
        assertFalse(shield.stream().anyMatch(v->v.contains("acknowledge")||v.endsWith(".setBlock")));
    }
    @Test void ordinaryFillAndUnscopedPlacementNeverReceiveTheShieldedException(){
        var fill=new com.google.gson.JsonObject();fill.addProperty("op","bucket_fill");fill.addProperty("projected_source_column",true);
        assertFalse(ProjectedSourceColumnGuard.shieldedWorkspace(null,fill));
        var ordinary=new com.google.gson.JsonObject();ordinary.addProperty("op","bucket_place");
        assertFalse(ProjectedSourceColumnGuard.shieldedWorkspace(null,ordinary));
    }
    @Test void realHostWhitelistExcludesCreepersAndAdmissionReportsZeroInput()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ProjectedSourceColumnGuard.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var method=node.methods.stream().filter(m->m.name.equals("shieldedActor")).findFirst().orElseThrow();var types=new HashSet<String>();
        for(var instruction:method.instructions)if(instruction instanceof LdcInsnNode ldc&&ldc.cst instanceof String text&&text.startsWith("minecraft:"))types.add(text);
        assertEquals(Set.of("minecraft:zombie","minecraft:skeleton","minecraft:slime"),types);
        var host=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(host,0);
        }
        assertTrue(host.methods.stream().filter(m->m.name.equals("bucketAdmissionDiagnostics")).anyMatch(m->{
            for(var instruction:m.instructions)if(instruction instanceof LdcInsnNode ldc&&"input_sent".equals(ldc.cst))return true;
            return false;
        }));
    }
    @Test void supplyRequiresTheColumnProofBeforeUsingItsShieldedActor()throws Exception{
        var before=calls("ProjectedSourceColumnSupplyGuard","requireBefore");
        assertTrue(before.contains("dev/twob2tkit/automation/ProjectedSourceColumnSupplyGuard.requireWorkspace"));
        assertTrue(before.contains("dev/twob2tkit/automation/SourceColumnSupplyPolicy.ready"));
        var ctor=calls("ProjectedSourceColumnSupplyGuard","<init>");
        assertTrue(ctor.contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.excludeRefillTarget"));
        var shield=calls("ProjectedSourceColumnSupplyGuard","shieldedWorkspace");
        assertTrue(shield.indexOf("dev/twob2tkit/automation/ProjectedSourceColumnSupplyGuard.requireWorkspace")
            <shield.indexOf("dev/twob2tkit/automation/ProjectedSourceColumnGuard.shieldedActor"));
        assertTrue(calls("BucketWaterAction","validateBeforeSend").contains("dev/twob2tkit/automation/ProjectedSourceColumnSupplyGuard.requireBefore"));
        assertTrue(calls("BucketWaterAction","poll").contains("dev/twob2tkit/automation/ProjectedSourceColumnSupplyGuard.current"));
    }
    @Test void sourceGuardChecksPlayerReserveAndLoadedWorldAndNeverAcknowledgesSafety()throws Exception{
        var require=calls("ProjectedSourceColumnGuard","requireWorkspace");
        assertTrue(calls("ProjectedSourceColumnGuard","require").contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.requireWorkspace"));
        assertTrue(require.contains("dev/twob2tkit/automation/ProjectedSourceColumnPolicy.actorReady"));
        assertTrue(require.contains("dev/twob2tkit/automation/ProjectedSourceColumnPolicy.rejection"));
        assertTrue(require.contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.loaded"));
        assertFalse(require.stream().anyMatch(v->v.contains("acknowledge")||v.endsWith(".setBlock")));
    }
}
