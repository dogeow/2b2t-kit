package dev.twob2tkit.chopper;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class ChopperMaterialWiringTest {
 private ClassNode read(String name)throws Exception{var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+name+".class")){new ClassReader(in).accept(n,0);}return n;}
 @Test void fixedTreeUsesTheExistingChopperAndChecksTheExactTreeBeforeStarting()throws Exception{
  var methods=read("chopper/AutoChopper").methods;
  var start=methods.stream().filter(m->m.name.equals("startMaterialFixed")).findFirst().orElseThrow();
  int verify=-1,begin=-1,i=0;
  for(var n:start.instructions){if(n instanceof MethodInsnNode c){if(c.name.equals("findFixed"))verify=i;if(c.name.equals("startMaterial"))begin=i;}i++;}
  assertTrue(verify>=0&&begin>verify);
  for(String method:java.util.List.of("isMineableTreeBlock","nearestLeaf","stillValid")){
   var m=methods.stream().filter(x->x.name.equals(method)).findFirst().orElseThrow();boolean contains=false;
   for(var n:m.instructions)if(n instanceof MethodInsnNode c&&c.owner.endsWith("ChopperFixedTreePlan")&&c.name.equals("contains"))contains=true;
   assertTrue(contains,method);
  }
 }
 @Test void materialCompletionWaitsForPickupAndReplantBeforeNextTree()throws Exception{
  var m=read("chopper/AutoChopper").methods.stream().filter(x->x.name.equals("tick")).findFirst().orElseThrow();
  int loot=-1,replant=-1,finish=-1,next=-1,i=0;
  for(var n:m.instructions){if(n instanceof MethodInsnNode c){if(c.owner.endsWith("ChopperLoot")&&c.name.equals("tick")&&loot<0)loot=i;if(c.name.equals("tryReplant"))replant=i;if(c.name.equals("lockNextTree"))next=i;}if(n instanceof FieldInsnNode f&&f.name.equals("finishRequested"))finish=i;i++;}
  assertTrue(loot>=0&&replant>loot&&finish>replant&&next>finish);
 }
 @Test void bridgeRequestsTreeCompletionInsteadOfStoppingAtInventoryThreshold()throws Exception{
  var m=read("automation/AutomationBridge").methods.stream().filter(x->x.name.equals("tick")).findFirst().orElseThrow();
  boolean requested=false,verified=false,waiting=false;int stops=0;
  for(var n:m.instructions)if(n instanceof MethodInsnNode c&&c.owner.endsWith("AutoChopper")){if(c.name.equals("waitingForTree"))waiting=true;if(c.name.equals("stop")){assertTrue(waiting);stops++;}requested|=c.name.equals("finishCurrentTree");verified|=c.name.equals("materialTargetFinished");}
  assertTrue(requested&&verified);assertEquals(1,stops);
 }
}
