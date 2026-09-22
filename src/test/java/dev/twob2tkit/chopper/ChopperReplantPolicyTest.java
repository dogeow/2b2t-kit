package dev.twob2tkit.chopper;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class ChopperReplantPolicyTest {
 @Test void completedTreesCanDeferBlockedReplant(){assertEquals(ChopperReplantPolicy.Blocked.DEFER_REPLANT,ChopperReplantPolicy.blocked(0));}
 @Test void unreachableLogsStillStopInsteadOfBeingSkipped(){assertEquals(ChopperReplantPolicy.Blocked.STOP_UNFINISHED_TREE,ChopperReplantPolicy.blocked(1));assertEquals(ChopperReplantPolicy.Blocked.STOP_UNFINISHED_TREE,ChopperReplantPolicy.blocked(80));}
 @Test void replantBranchesOnApproachResultBeforeUsingTreeState()throws Exception{
  var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/chopper/AutoChopper.class")){new ClassReader(in).accept(c,0);}
  var m=c.methods.stream().filter(x->x.name.equals("tryReplant")).findFirst().orElseThrow();
  for(var n:m.instructions)if(n instanceof MethodInsnNode call&&call.name.equals("approach")){
   var next=n.getNext();while(next!=null&&next.getOpcode()<0)next=next.getNext();assertInstanceOf(JumpInsnNode.class,next);return;
  }fail("Approach call absent");
 }
}
