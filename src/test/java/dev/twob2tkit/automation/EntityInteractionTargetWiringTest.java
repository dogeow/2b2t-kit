package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class EntityInteractionTargetWiringTest {
    private ClassNode bridge()throws Exception{
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        return node;
    }
    private List<AbstractInsnNode> branch(ClassNode node){
        var dispatch=node.methods.stream().filter(m->m.name.equals("dispatch")).findFirst().orElseThrow();
        AbstractInsnNode marker=null;
        for(var i:dispatch.instructions)if(i instanceof LdcInsnNode s&&"interact_entity".equals(s.cst)){marker=i;break;}
        assertNotNull(marker);JumpInsnNode boundary=null;
        for(var i=marker.getNext();i!=null;i=i.getNext())if(i instanceof JumpInsnNode j){boundary=j;break;}
        assertNotNull(boundary);var result=new ArrayList<AbstractInsnNode>();
        for(var i=boundary.getNext();i!=boundary.label;i=i.getNext()){assertNotNull(i);result.add(i);}
        return result;
    }
    @Test void uuidHandReachAndActualRayChecksPrecedeMerchantOpeningAndInput()throws Exception{
        var node=bridge();var instructions=branch(node);var calls=new ArrayList<String>();
        for(var i:instructions)if(i instanceof MethodInsnNode m)calls.add(m.name);
        assertTrue(calls.containsAll(List.of("getUUID","getMainHandItem","entityInteractionRange","find","opening","interact")));
        assertTrue(calls.indexOf("getUUID")<calls.indexOf("find"));
        assertTrue(calls.indexOf("getMainHandItem")<calls.indexOf("find"));
        assertTrue(calls.indexOf("entityInteractionRange")<calls.indexOf("find"));
        assertTrue(calls.indexOf("find")<calls.indexOf("opening"));
        assertTrue(calls.indexOf("opening")<calls.indexOf("interact"));
        assertFalse(calls.contains("hasLineOfSight"));
        boolean rayPredicateWired=false;
        for(var i:instructions)if(i instanceof InvokeDynamicInsnNode dynamic){
            for(var arg:dynamic.bsmArgs)if(arg instanceof Handle handle&&handle.getOwner().equals(node.name)){
                var lambda=node.methods.stream().filter(m->m.name.equals(handle.getName())&&m.desc.equals(handle.getDesc())).findFirst().orElseThrow();
                for(var op:lambda.instructions)if(op instanceof MethodInsnNode call&&call.name.equals("entityHitVisible"))rayPredicateWired=true;
            }
        }
        assertTrue(rayPredicateWired);
    }
    @Test void intendedHitRayKeepsColliderAndNoFluidOcclusionPolicy()throws Exception{
        var method=bridge().methods.stream().filter(m->m.name.equals("entityHitVisible")).findFirst().orElseThrow();
        var fields=new ArrayList<String>();var calls=new ArrayList<String>();
        for(var i:method.instructions){
            if(i instanceof FieldInsnNode f)fields.add(f.name);
            if(i instanceof MethodInsnNode m)calls.add(m.name);
        }
        assertTrue(fields.containsAll(List.of("COLLIDER","NONE","MISS")));
        assertTrue(calls.contains("clip"));assertFalse(calls.contains("interact"));
    }
}
