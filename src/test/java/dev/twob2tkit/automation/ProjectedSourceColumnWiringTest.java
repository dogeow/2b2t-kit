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
        assertTrue(node.methods.stream().filter(m->m.name.equals("snapshot")).anyMatch(m->{
            for(var instruction:m.instructions)if(instruction instanceof LdcInsnNode ldc
                    &&"projected_source_column_protocol".equals(ldc.cst))return true;
            return false;
        }));
    }
    @Test void sourceGuardChecksPlayerReserveAndLoadedWorldAndNeverAcknowledgesSafety()throws Exception{
        var require=calls("ProjectedSourceColumnGuard","require");
        assertTrue(require.contains("dev/twob2tkit/automation/ProjectedSourceColumnPolicy.actorReady"));
        assertTrue(require.contains("dev/twob2tkit/automation/ProjectedSourceColumnPolicy.rejection"));
        assertTrue(require.contains("dev/twob2tkit/automation/ProjectedSourceColumnGuard.loaded"));
        assertFalse(require.stream().anyMatch(v->v.contains("acknowledge")||v.endsWith(".setBlock")));
    }
}
