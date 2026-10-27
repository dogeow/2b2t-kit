package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionMaterialDemandScopeTest {
    @Test void materialMaskDoesNotShrinkWholeProjectionProgress()throws Exception{
        var node=new ClassNode();try(var input=getClass().getResourceAsStream("/dev/twob2tkit/builder/ProjectionBuildJob.class")){assertNotNull(input);new ClassReader(input).accept(node,0);}
        var recount=node.methods.stream().filter(m->m.name.equals("recount")).findFirst().orElseThrow();
        int matched=-1,blocked=-1,scope=-1,merge=-1,index=0;
        for(var instruction:recount.instructions){
            if(instruction instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTFIELD){
                if(f.name.equals("matched"))matched=index;if(f.name.equals("blockedBlocks"))blocked=index;assertNotEquals("total",f.name);
            }
            if(instruction instanceof MethodInsnNode call){
                if(call.name.equals("projectionBatchAllows")){
                    scope=index;var next=instruction.getNext();while(next.getOpcode()<0)next=next.getNext();assertTrue(next instanceof JumpInsnNode,"The mask must control whether demand is counted");
                }
                if(call.name.equals("merge"))merge=index;
            }
            index++;
        }
        assertTrue(matched>=0&&blocked>=0&&scope>matched&&scope>blocked&&merge>scope,
            "All model cells must update progress before only in-scope cells add material demand");
    }
}
