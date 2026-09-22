package dev.twob2tkit.automation;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class WorkBlockApproachTest {
 @Test void overheadBlocksHaveCandidatesWithEyesBelowTheirBottomFace(){
  var target=new BlockPos(18,69,33);boolean possible=false;
  for(var feet:BuildSupplyTask.approachCandidates(target)){
   double eye=feet.getY()+.02+1.62;
   if(eye<target.getY()&&target.getY()-eye<4&&Math.abs(feet.getX()-target.getX())<=1)possible=true;
  }
  assertTrue(possible,"An underside approach is impossible if every candidate eye is inside or above the block");
 }
 @Test void normalFloorWorkstationsStillHaveNearbyStandingCandidates(){
  var target=new BlockPos(17,65,36);boolean possible=false;
  for(var feet:BuildSupplyTask.approachCandidates(target))if(feet.equals(new BlockPos(16,65,36)))possible=true;
  assertTrue(possible);
 }
 @Test void aPlayerCanCollectAnItemNearTheirHeadWithoutStandingOnItsSupportingBlock(){
  var item=new AABB(17.91,69,834.75,18.16,69.25,835);
  var side=new AABB(17.2,67.02,835.2,17.8,68.82,835.8);
  assertTrue(BuildSupplyTask.pickupIntersects(side,item));
  var tooLow=new AABB(17.2,65.02,835.2,17.8,66.82,835.8);
  assertFalse(BuildSupplyTask.pickupIntersects(tooLow,item));
 }
 @Test void supplyUsesTheReloadableMotionAndStopsBeforeTerminalMenuChecks()throws Exception {
  var node=new org.objectweb.asm.tree.ClassNode();
  try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/BuildSupplyTask.class")){new org.objectweb.asm.ClassReader(in).accept(node,0);}
  var move=node.methods.stream().filter(m->m.name.equals("move")).findFirst().orElseThrow();
  boolean usesMotion=false;
  for(var op:move.instructions)if(op instanceof org.objectweb.asm.tree.MethodInsnNode call&&call.owner.equals("dev/twob2tkit/runtime/api/BuildNavigation")&&call.name.equals("motion"))usesMotion=true;
  assertTrue(usesMotion,"Depot movement must use the same hot engine as projection travel");
  var tick=node.methods.stream().filter(m->m.name.equals("tick")).findFirst().orElseThrow();
  int instructionsBeforeFirstReturn=0;boolean closedGuard=false;
  for(var op:tick.instructions){
   if(op instanceof org.objectweb.asm.tree.FieldInsnNode field&&field.name.equals("closed"))closedGuard=true;
   if(op.getOpcode()==org.objectweb.asm.Opcodes.RETURN)break;
   instructionsBeforeFirstReturn++;
  }
  assertTrue(closedGuard&&instructionsBeforeFirstReturn<30,"A completed or failed input phase must return before accessing any container");
 }
}
