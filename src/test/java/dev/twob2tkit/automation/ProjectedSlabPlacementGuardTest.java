package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.shapes.Shapes;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectedSlabPlacementGuardTest {
 @Test void fullSupportKeepsVisibleRaysBelowAndAboveTheAmbiguousHalfBoundary(){
  for(var face:new Direction[]{Direction.NORTH,Direction.SOUTH,Direction.EAST,Direction.WEST}){
   var shape=Shapes.block();var points=BlockFaceTarget.points(shape,face);
   for(double height:new double[]{.2,.8}){
    var point=points.stream().filter(p->Math.abs(p.y-height)<1e-6).findFirst().orElseThrow();
    var eye=point.add(face.getStepX()*3,0,face.getStepZ()*3);
    var hit=shape.clip(eye,point,BlockPos.ZERO);assertNotNull(hit);assertEquals(face,hit.getDirection());
    assertEquals(height,hit.getLocation().y,1e-6);
   }
  }
 }
 @Test void flagIsExplicitAndStrict(){
  var r=new JsonObject();assertFalse(ProjectedSlabPlacementGuard.requested(r));r.addProperty("projected_slab_place",true);assertTrue(ProjectedSlabPlacementGuard.requested(r));
  r.addProperty("projected_slab_place","true");assertThrows(IllegalArgumentException.class,()->ProjectedSlabPlacementGuard.requested(r));
 }
 private ClassNode node(String name)throws Exception{
  var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/"+name+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n;
 }
 @Test void exactVanillaPredictionRejectsMergingTheSupportOrWrongHalf()throws Exception{
  var m=node("ProjectedSlabPlacementGuard").methods.stream().filter(v->v.name.equals("predicts")).findFirst().orElseThrow();
  var calls=java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
  assertTrue(calls.contains("getStateForPlacement"));assertTrue(calls.contains("getClickedPos"));assertTrue(calls.contains("equals"));
  assertFalse(calls.contains("setBlock"));
 }
 @Test void loadingModelAirEntitiesAndActualRayAreRecheckedBeforeNormalUse()throws Exception{
  var n=node("ProjectedSlabPlacementGuard");var m=n.methods.stream().filter(v->v.name.equals("require")).findFirst().orElseThrow();
  var calls=java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
  for(String name:new String[]{"isServerChunk","inVisibleLayer","isAir","getBlockEntity","getEntities","predicts","matches"})assertTrue(calls.contains(name),name);
  var bridge=node("AutomationBridge");long checks=bridge.methods.stream().flatMap(v->java.util.stream.StreamSupport.stream(v.instructions.spliterator(),false)).filter(i->i instanceof MethodInsnNode c&&c.owner.endsWith("/ProjectedSlabPlacementGuard")&&(c.name.equals("visible")||c.name.equals("require"))).count();assertEquals(2,checks);
 }
}
