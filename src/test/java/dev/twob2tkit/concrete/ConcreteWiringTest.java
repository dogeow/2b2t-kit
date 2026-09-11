package dev.twob2tkit.concrete;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ConcreteWiringTest {
    private MethodNode method(String cls,String name)throws Exception{
        ClassNode n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode x)r.add(x.name);return r;}
    @Test void guardPrecedesConverterAndConverterPrecedesNavigation()throws Exception{
        var c=calls(method("KitClient","tickNavigation"));assertTrue(c.indexOf("beforeGuard")<c.indexOf("beforeInput"));assertTrue(c.contains("pause"));
        var m=method("mixin/MinecraftTickMixin","kit$ownedMining");assertTrue(calls(m).containsAll(List.of("concrete","ownsMining","cancel")));
    }
    @Test void pausePreservesPendingBreakVerificationButCancelsNativeMining()throws Exception{
        var p=method("concrete/ConcreteMaker","pause");assertTrue(calls(p).containsAll(List.of("stopDestroyBlock","releaseModules")));
        var writes=new ArrayList<String>();for(var i:p.instructions)if(i instanceof FieldInsnNode f && f.getOpcode()==Opcodes.PUTFIELD)writes.add(f.name);
        assertTrue(writes.contains("mineStarted"));assertFalse(writes.contains("breaking"));
    }
    @Test void cancellationRestoresOwnedModulesAndNeverSetsWorldBlocks()throws Exception{
        assertTrue(calls(method("concrete/ConcreteMaker","stop")).contains("pause"));
        var tick=calls(method("concrete/ConcreteMaker","tick"));assertTrue(tick.containsAll(List.of("action","getBlockEntity","startDestroyBlock","continueDestroyBlock")));
        assertFalse(tick.contains("setBlock"));assertTrue(tick.indexOf("action")<tick.indexOf("startDestroyBlock"));
        assertTrue(calls(method("concrete/ConcreteMaker","placeSneaking")).contains("useItemOn"));
    }
}
