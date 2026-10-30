package dev.twob2tkit.combat;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class MinorThermalWorkWiringTest {
    List<String> calls(String cls,String method)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var m=node.methods.stream().filter(x->x.name.equals(method)).findFirst().orElseThrow();var result=new ArrayList<String>();
        for(var i:m.instructions)if(i instanceof MethodInsnNode c)result.add(c.owner+"."+c.name);
        return result;
    }
    @Test void nativeCriticalExitPrecedesWorkExemptionAndExemptionDoesNotClearHold()throws Exception{
        var c=calls("combat/EmergencyExit","observeHealth");
        assertTrue(c.indexOf("dev/twob2tkit/combat/EmergencyExit.begin")<c.indexOf("dev/twob2tkit/combat/EmergencyExit.minorThermalWorkAllowed"));
        var gate=calls("combat/EmergencyExit","minorThermalWorkAllowed");
        assertTrue(gate.contains("dev/twob2tkit/combat/MinorThermalWorkPolicy.allow"));
        assertFalse(gate.stream().anyMatch(x->x.contains("clear")||x.contains("acknowledge")));
    }
    @Test void humanRecoveryRetainsGrantValidationAndUsesSameLiveThermalEvidence()throws Exception{
        var c=calls("automation/AutomationBridge","confirmExplicitRecovery");
        assertTrue(c.contains("dev/twob2tkit/combat/EmergencyExit.minorThermalWorkAllowed"));
        assertTrue(c.contains("dev/twob2tkit/combat/RecoveryConfirmationPolicy.require"));
        assertTrue(c.indexOf("dev/twob2tkit/combat/RecoveryConfirmationPolicy.require")<c.indexOf("dev/twob2tkit/combat/EmergencyExit.acknowledgeExplicitChat"));
    }
}
