package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import java.util.HashSet;
import static org.junit.jupiter.api.Assertions.*;

class BelowFlowMiningIntegrationTest {
    @Test void optInIsStrictlyBooleanAndAbsentByDefault(){
        var request=new JsonObject();assertFalse(BelowFlowMiningGuard.requested(request));
        request.addProperty("flowing_water_below",false);assertFalse(BelowFlowMiningGuard.requested(request));
        request.addProperty("flowing_water_below",true);assertTrue(BelowFlowMiningGuard.requested(request));
        request.addProperty("flowing_water_below","true");assertThrows(IllegalArgumentException.class,()->BelowFlowMiningGuard.requested(request));
    }
    @Test void compiledBridgeChecksAdmissionAndRunningMining()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var methods=new HashSet<String>();
        for(var method:node.methods)for(var instruction:method.instructions)
            if(instruction instanceof MethodInsnNode call&&call.owner.equals("dev/twob2tkit/automation/BelowFlowMiningGuard")&&call.name.equals("require"))methods.add(method.name);
        assertEquals(2,methods.size(),"Both initial dispatch and ongoing mining must validate the guard");
    }
}
