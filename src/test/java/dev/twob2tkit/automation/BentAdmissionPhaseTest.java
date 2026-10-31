package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
class BentAdmissionPhaseTest {
 @Test void firstDryPourUsesTheBeforeGeometryAndConfirmedSourceUsesAfterGeometry(){
  var goal=List.of(0,1,2,3,4,5,6,7);var dry=List.of(-1,-1,-1,-1,-1,-1,-1,-1);
  assertTrue(ProjectedBentChannelPolicy.admissionBefore(false,-1));
  assertTrue(ProjectedBentChannelPolicy.levels(goal,dry,ProjectedBentChannelPolicy.admissionBefore(false,-1)));
  assertFalse(ProjectedBentChannelPolicy.levels(goal,dry,false));
  assertFalse(ProjectedBentChannelPolicy.admissionBefore(false,0));
  assertTrue(ProjectedBentChannelPolicy.levels(goal,goal,ProjectedBentChannelPolicy.admissionBefore(false,0)));
 }
 @Test void seedAndCollectionKeepTheirExactPreUseShapes(){
  var goal=List.of(0,1,2,3,4,5,6,7);var partial=List.of(0,1,-1,-1,-1,-1,-1,-1);var seed=List.of(0,0,0,1,2,3,4,5);var middle=List.of(0,0,1,2,3,4,5,6);
  assertTrue(ProjectedBentChannelPolicy.seedLevels(goal,partial,ProjectedBentChannelPolicy.admissionBefore(false,-1)));
  assertTrue(ProjectedBentChannelPolicy.collectLevels(goal,seed,2,ProjectedBentChannelPolicy.admissionBefore(true,0)));
  assertFalse(ProjectedBentChannelPolicy.collectLevels(goal,middle,2,ProjectedBentChannelPolicy.admissionBefore(true,0)));
  assertTrue(ProjectedBentChannelPolicy.collectLevels(goal,middle,2,ProjectedBentChannelPolicy.admissionBefore(true,1)));
 }
 @Test void realAdmissionInfersPhaseBeforeCheckingChamberAndActor()throws Exception{
  var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ProjectedBentChannelGuard.class")){assertNotNull(in);new ClassReader(in).accept(n,0);}
  var m=n.methods.stream().filter(v->v.name.equals("shieldedWorkspace")).findFirst().orElseThrow();
  var calls=java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
  assertTrue(calls.indexOf("admissionBefore")<calls.indexOf("require"));assertTrue(calls.indexOf("require")<calls.indexOf("shieldedActor"));assertFalse(calls.contains("setBlock"));
 }
}
