package dev.twob2tkit.automation;
import java.util.*;
import net.minecraft.core.*;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.material.FluidState;
import net.minecraft.world.phys.*;
import net.minecraft.world.phys.shapes.CollisionContext;
import org.junit.jupiter.api.*;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectedDrainAimTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 static final BlockPos TARGET=new BlockPos(0,62,0);
 static class Scene implements BlockGetter {
  final Map<BlockPos,BlockState> blocks=new HashMap<>();
  public BlockEntity getBlockEntity(BlockPos p){return null;}
  public BlockState getBlockState(BlockPos p){return blocks.getOrDefault(p,Blocks.AIR.defaultBlockState());}
  public FluidState getFluidState(BlockPos p){return getBlockState(p).getFluidState();}
  public int getHeight(){return 384;}public int getMinY(){return -64;}
 }
 Scene floor(){var scene=new Scene();var dry=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(BlockStateProperties.SLAB_TYPE,SlabType.TOP);
  for(int x=-4;x<=4;x++)for(int z=-4;z<=4;z++)scene.blocks.put(new BlockPos(x,62,z),dry);
  scene.blocks.put(TARGET,dry.setValue(BlockStateProperties.WATERLOGGED,true));return scene;
 }
 BlockHitResult ray(Scene s,Vec3 eye,Vec3 end){return s.clip(new ClipContext(eye,end,ClipContext.Block.OUTLINE,ClipContext.Fluid.SOURCE_ONLY,CollisionContext.empty()));}
 @Test void surfaceRayReachesAcrossTheSameFloorWhereCentreAimHitsAnInterveningSlab(){
  var s=floor();var eye=new Vec3(.5,64.77,3.5);
  assertNotEquals(TARGET,ray(s,eye,Vec3.atCenterOf(TARGET)).getBlockPos());
  var hit=ProjectedDrainAim.visible(s,eye,TARGET,4.3,CollisionContext.empty());assertNotNull(hit);assertEquals(TARGET,hit.getBlockPos());assertTrue(eye.distanceTo(hit.getLocation())<=4.3);
 }
 @Test void exposedSlabEdgesCanBeUsedWithoutBreakingTheTorchAbove(){
  var s=floor();s.blocks.put(TARGET.above(),Blocks.TORCH.defaultBlockState());var eye=new Vec3(.5,64.77,.5);
  assertEquals(TARGET.above(),ray(s,eye,Vec3.atCenterOf(TARGET)).getBlockPos());
  var hit=ProjectedDrainAim.visible(s,eye,TARGET,4.3,CollisionContext.empty());assertNotNull(hit);assertEquals(TARGET,hit.getBlockPos());assertEquals(Blocks.TORCH,s.getBlockState(TARGET.above()).getBlock());
 }
 @Test void aCorrectSolidStairCoverIsNotBypassed(){
  var s=floor();s.blocks.put(TARGET.above(),Blocks.COBBLESTONE_STAIRS.defaultBlockState().setValue(BlockStateProperties.HORIZONTAL_FACING,Direction.SOUTH));
  assertNull(ProjectedDrainAim.visible(s,new Vec3(.5,64.77,-.5),TARGET,4.3,CollisionContext.empty()));
 }
 @Test void realReachRemainsMandatory(){var s=floor();assertNull(ProjectedDrainAim.visible(s,new Vec3(.5,75,.5),TARGET,4.3,CollisionContext.empty()));assertNull(ProjectedDrainAim.visible(s,new Vec3(.5,64.77,.5),TARGET,Double.NaN,CollisionContext.empty()));}
 ClassNode code(String n)throws Exception{var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/"+n+".class")){assertNotNull(in);new ClassReader(in).accept(c,0);}return c;}
 @Test void drainAimKeepsVanillaRayAndEntityChecksWithoutChangingPlainSourceAiming()throws Exception{
  var aim=code("BucketWaterAction").methods.stream().filter(m->m.name.equals("aim")).findFirst().orElseThrow();Set<String> names=new HashSet<>();boolean scoped=false;
  for(var i:aim.instructions){if(i instanceof MethodInsnNode c)names.add(c.name);if(i instanceof FieldInsnNode f)scoped|=f.name.equals("projectedDrain");}
  assertTrue(scoped);assertTrue(names.containsAll(Set.of("visible","inside","atCenterOf","clip","entityRayClear")));
 }
 @Test void preflightDiagnosticsAreWrittenOnlyBeforeTaskAssignmentAndCannotCoverTheUse()throws Exception{
  var n=code("AutomationBridge");boolean found=false;
  for(var method:n.methods)for(var tc:method.tryCatchBlocks){
   boolean ctor=false,aim=false,use=false;
   for(AbstractInsnNode i=tc.start;i!=tc.end&&i!=null;i=i.getNext())if(i instanceof MethodInsnNode c){ctor|=c.owner.endsWith("BucketWaterAction")&&c.name.equals("<init>");aim|=c.owner.endsWith("BucketWaterAction")&&c.name.equals("aim");use|=c.name.equals("useOnce");}
   if(ctor&&aim){boolean diagnostic=false,stage=false;
    for(AbstractInsnNode i=tc.handler;i!=null;i=i.getNext()){
     if(i instanceof MethodInsnNode c)diagnostic|=c.name.equals("bucketAdmissionDiagnostics");
     if(i instanceof LdcInsnNode c)stage|="before_task_assignment".equals(c.cst);
     if(i.getOpcode()==Opcodes.ATHROW)break;
    }
    if(diagnostic&&stage){found=true;assertFalse(use);
     for(AbstractInsnNode i=tc.start;i!=tc.end&&i!=null;i=i.getNext())if(i instanceof FieldInsnNode f&&f.getOpcode()==Opcodes.PUTSTATIC)assertNotEquals("bucketWaterTask",f.name);
    }
   }
  }assertTrue(found);
 }
}
