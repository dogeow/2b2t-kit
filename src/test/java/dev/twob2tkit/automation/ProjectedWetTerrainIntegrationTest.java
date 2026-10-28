package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import java.util.HashSet;
import static org.junit.jupiter.api.Assertions.*;

class ProjectedWetTerrainIntegrationTest {
    @Test void ordinaryMiningDoesNotOptInAndNonBooleanFlagsFailClosed(){
        var r=new JsonObject();assertFalse(ProjectedWetTerrainGuard.requested(r));
        r.addProperty("projected_wet_terrain",false);assertFalse(ProjectedWetTerrainGuard.requested(r));
        r.addProperty("projected_wet_terrain",true);assertTrue(ProjectedWetTerrainGuard.requested(r));
        r.addProperty("projected_wet_terrain","true");assertThrows(IllegalArgumentException.class,()->ProjectedWetTerrainGuard.requested(r));
        r.addProperty("projected_wet_terrain",1);assertThrows(IllegalArgumentException.class,()->ProjectedWetTerrainGuard.requested(r));
    }
    @Test void compiledHostRevalidatesAtAdmissionAndThroughoutMining()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var sites=new HashSet<String>();
        for(var method:node.methods)for(var instruction:method.instructions)
            if(instruction instanceof MethodInsnNode call&&call.owner.equals("dev/twob2tkit/automation/ProjectedWetTerrainGuard")&&call.name.equals("require"))sites.add(method.name);
        assertEquals(2,sites.size(),"An admitted request must not outlive its safety checks");
    }
}
