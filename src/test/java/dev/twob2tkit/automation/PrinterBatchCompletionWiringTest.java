package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class PrinterBatchCompletionWiringTest {
    private MethodNode method(String cls,String name,String descriptor)throws Exception{
        var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){
            assertNotNull(in);new ClassReader(in).accept(c,0);
        }
        return c.methods.stream().filter(m->m.name.equals(name)&&(descriptor==null||m.desc.equals(descriptor))).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode m){
        var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode n)r.add(n.name);return r;
    }
    @Test void completionGateNeedsTheCurrentMaterialOwnerAndNonemptyCurrentProjectionMask()throws Exception{
        var names=calls(method("automation/AutomationBridge","boundedPrinterComplete",null));
        assertTrue(names.containsAll(List.of("currentMaterialRequest","active","count","projectionBatchCurrent","positions","batchServerConfirmed")));
        assertTrue(names.indexOf("currentMaterialRequest")<names.indexOf("batchServerConfirmed"));
        assertTrue(names.indexOf("projectionBatchCurrent")<names.indexOf("batchServerConfirmed"));
    }
    @Test void earlyEndReusesNormalFinishAndDeadlineReturnsWaiting()throws Exception{
        var m=method("automation/AutomationBridge","tick",null);boolean early=false,legacy=false;
        for(var i:m.instructions)if(i instanceof LdcInsnNode n&&n.cst instanceof String s){
            early|=s.equals("all bounded printer targets server-confirmed; batch finished early");
            legacy|=s.equals("printer interval ended without complete current bounded-mask server confirmation");
        }
        assertTrue(early);assertTrue(legacy);assertTrue(calls(m).contains("boundedPrinterComplete"));
        assertTrue(calls(m).contains("finish"));
    }
    @Test void earlyPrinterGateUsesOnlyPacketProofAndSettledNativeQueue()throws Exception{
        var names=calls(method("automation/ProfessionalPrinter","batchServerConfirmed",null));
        assertTrue(names.containsAll(List.of("complete","readyForTravel")));
        for(String clientEvidence:List.of("getBlockState","inventoryCounts","getInventory","schematicWorld"))assertFalse(names.contains(clientEvidence));
    }
    @Test void correctionsAreObservedBeforeThePendingTargetFilterAndBothAcksStillRun()throws Exception{
        var names=calls(method("automation/ProfessionalPrinter","serverBlock",null));
        assertEquals("serverBlock",names.get(0));
        assertTrue(names.indexOf("serverBlock")<names.indexOf("sent"));
        assertEquals(3,names.stream().filter(n->n.equals("acknowledge")).count());
        assertTrue(names.contains("equals")); // Exact final state; legacy matcher remains for pacing.
        assertTrue(names.contains("matches"));
    }
    @Test void startResetsProofAndDefaultStartUsesNoBatchTargets()throws Exception{
        assertTrue(calls(method("automation/ProfessionalPrinter","start","(ZLjava/util/Collection;)V")).contains("begin"));
        var names=calls(method("automation/ProfessionalPrinter","start","(Z)V"));
        assertTrue(names.containsAll(List.of("of","start")));
        assertTrue(calls(method("automation/ProfessionalPrinter","nativeProposalQueued",null)).contains("queued"));
    }
    @Test void packetCallbacksUseCurrentConnectionBeforeCreditingPrinter()throws Exception{
        for(String name:List.of("kit$concreteBlockUpdate","kit$concreteSectionUpdate")){
            var m=method("mixin/ConcreteBlockUpdatesMixin",name,null);int connection=-1;JumpInsnNode guard=null;
            for(var i:m.instructions){
                if(i instanceof MethodInsnNode n&&n.name.equals("getConnection"))connection=m.instructions.indexOf(i);
                if(connection>=0&&i instanceof JumpInsnNode j&&j.getOpcode()==Opcodes.IF_ACMPNE){guard=j;break;}
            }
            assertNotNull(guard);int start=m.instructions.indexOf(guard),end=m.instructions.indexOf(guard.label);
            assertTrue(end>start);
            boolean ppInside=false;
            for(int i=start+1;i<end;i++){
                var n=m.instructions.get(i);
                if(n instanceof MethodInsnNode call&&call.owner.equals("dev/twob2tkit/automation/ProfessionalPrinter"))ppInside=true;
                if(n instanceof InvokeDynamicInsnNode dyn)for(var arg:dyn.bsmArgs)
                    if(arg instanceof org.objectweb.asm.Handle h&&h.getOwner().equals("dev/twob2tkit/automation/ProfessionalPrinter"))ppInside=true;
            }
            assertTrue(ppInside);
        }
    }
    @Test void normalFinishStillStopsPrinterAndRestoresInputs()throws Exception{
        var names=calls(method("automation/AutomationBridge","finish",null));
        assertTrue(names.containsAll(List.of("stop","restoreArrival","releaseWalk")));
    }
}
