package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class MaterialControlPolicyTest {
    @Test void changedManualRevisionRevokesCollection(){assertTrue(MaterialControlPolicy.owned(3,3,true));assertFalse(MaterialControlPolicy.owned(3,4,true));}
    @Test void differentDefenseModeDoesNotKeepTheCollectorOwner(){assertFalse(MaterialControlPolicy.owned(3,3,false));}
    @Test void manualNewTasksHandOffBeforeStartingTheirWork()throws Exception{
        var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/KitClient.class")){new ClassReader(in).accept(c,0);}
        for(String name:new String[]{"prepareForCruise","prepareForMachine","prepareForBorer","toggleProjectionBuild"}){
            var m=c.methods.stream().filter(x->x.name.equals(name)).findFirst().orElseThrow();MethodInsnNode first=null;
            for(var n:m.instructions)if(n instanceof MethodInsnNode call){first=call;break;}
            assertNotNull(first);assertEquals("userTaskStarting",first.name);
        }
    }
}
