package dev.twob2tkit.automation;

import java.util.ArrayList;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class ControlledWaterReleaseWiringTest {
    private ClassNode bridge()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}return node;
    }
    private int call(MethodNode method,String owner,String name){
        for(int i=0;i<method.instructions.size();i++)if(method.instructions.get(i)instanceof MethodInsnNode c&&c.owner.endsWith(owner)&&c.name.equals(name))return i;
        return -1;
    }
    @Test void bothAdmissionAndContinuationValidateContainmentBeforeNativeMining()throws Exception{
        var node=bridge();var dispatch=node.methods.stream().filter(m->m.name.equals("dispatch")).findFirst().orElseThrow();
        int require=call(dispatch,"ControlledWaterReleaseGuard","require"),begin=call(dispatch,"SingleBlockMiningConfirmation","begin");assertTrue(require>=0&&begin>require);assertTrue(call(dispatch,"ControlledWaterReleaseGuard","requested")<require);
        var mining=node.methods.stream().filter(m->call(m,"SingleBlockMiningConfirmation","mine")>=0).findFirst().orElseThrow();assertTrue(call(mining,"ControlledWaterReleaseGuard","require")>=0);assertTrue(call(mining,"ControlledWaterReleaseGuard","require")<call(mining,"SingleBlockMiningConfirmation","mine"));assertTrue(call(mining,"ControlledWaterReleaseGuard","require")<call(mining,"AutomationBridge","singleBlockConfirmed"));
    }
    @Test void receiptsAttestTheExplicitModeAndTheProtocolIsAdvertised()throws Exception{
        var node=bridge();var proof=node.methods.stream().filter(m->m.name.equals("singleBlockConfirmation")).findFirst().orElseThrow();assertTrue(call(proof,"ControlledWaterReleaseGuard","requested")>=0);
        var literals=new ArrayList<String>();for(var m:node.methods)for(var ins:m.instructions)if(ins instanceof LdcInsnNode ldc&&ldc.cst instanceof String text)literals.add(text);
        assertTrue(literals.contains("controlled_water_release_protocol"));assertTrue(literals.contains("controlled_water_release"));assertTrue(literals.contains("Fluid next to target is protected"));
    }
}
