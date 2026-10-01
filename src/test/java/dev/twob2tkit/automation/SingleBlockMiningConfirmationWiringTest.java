package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class SingleBlockMiningConfirmationWiringTest {
    private MethodNode method(String cls,String name)throws Exception {
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method) {
        var calls=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode call)calls.add(call.name);
        return calls;
    }
    @Test void nativeMiningUsesNormalInterfacesAndCapturesGeneratedSequencesEvenOnFailure()throws Exception {
        var m=method("automation/SingleBlockMiningConfirmation","mine");var names=calls(m);
        assertTrue(names.containsAll(List.of("requireOwner","hold","currentSequence","startDestroyBlock","continueDestroyBlock","sent","clientState")));
        assertTrue(names.indexOf("hold")<names.indexOf("startDestroyBlock"));
        assertFalse(m.tryCatchBlocks.isEmpty()); // Partial native sends must retain the claim in finally.
    }
    @Test void proofRequiresLiveOwnerLoadedTargetAndNoRetainedPrediction()throws Exception {
        var names=calls(method("automation/SingleBlockMiningConfirmation","confirmed"));
        assertTrue(names.containsAll(List.of("owns","hasChunkAt","getBlockState","predictionPending","confirmed")));
    }
    @Test void bothPacketFormsAndAckNeedTheCurrentListenerBeforeCreditingSingleBlockProof()throws Exception {
        for(var name:List.of("kit$concreteBlockUpdate","kit$concreteSectionUpdate","kit$singleBlockChangedAck")){
            var m=method("mixin/ConcreteBlockUpdatesMixin",name);JumpInsnNode guard=null;boolean connection=false;
            for(var i:m.instructions){
                if(i instanceof MethodInsnNode call&&call.name.equals("getConnection"))connection=true;
                if(connection&&i instanceof JumpInsnNode jump&&jump.getOpcode()==Opcodes.IF_ACMPNE){guard=jump;break;}
            }
            assertNotNull(guard);boolean proof=false;int end=m.instructions.indexOf(guard.label);
            for(int i=m.instructions.indexOf(guard)+1;i<end;i++){
                var instruction=m.instructions.get(i);
                if(instruction instanceof MethodInsnNode call&&call.owner.equals("dev/twob2tkit/automation/SingleBlockMiningConfirmation"))proof=true;
                if(instruction instanceof InvokeDynamicInsnNode dynamic)for(var argument:dynamic.bsmArgs)
                    if(argument instanceof org.objectweb.asm.Handle handle&&handle.getOwner().equals("dev/twob2tkit/mixin/ConcreteBlockUpdatesMixin"))proof=true;
            }
            assertTrue(proof);
            var annotations=new ArrayList<AnnotationNode>();
            if(m.visibleAnnotations!=null)annotations.addAll(m.visibleAnnotations);
            if(m.invisibleAnnotations!=null)annotations.addAll(m.invisibleAnnotations);
            var inject=annotations.stream().filter(a->a.desc.equals("Lorg/spongepowered/asm/mixin/injection/Inject;")).findFirst().orElseThrow();
            var at=(List<?>)inject.values.get(inject.values.indexOf("at")+1);
            assertTrue(at.stream().anyMatch(value->value instanceof AnnotationNode annotation&&annotation.values.contains("TAIL")));
        }
    }
}
