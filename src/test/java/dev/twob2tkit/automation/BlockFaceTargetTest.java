package dev.twob2tkit.automation;
import net.minecraft.core.*;
import net.minecraft.world.level.EmptyBlockGetter;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.properties.*;
import net.minecraft.world.phys.*;
import net.minecraft.world.phys.shapes.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
class BlockFaceTargetTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 @Test void topTrapdoorCanBeHitFromBelowWhereTheOldCubeFaceMissed(){
  var shape=Blocks.OAK_TRAPDOOR.defaultBlockState().setValue(BlockStateProperties.HALF,Half.TOP).getShape(EmptyBlockGetter.INSTANCE,BlockPos.ZERO);
  var eye=new Vec3(.5,-2,.5);
  assertNull(shape.clip(eye,new Vec3(.5,.001,.5),BlockPos.ZERO));
  var point=BlockFaceTarget.points(shape,Direction.DOWN).getFirst();assertTrue(point.y>.8125&&point.y<.813);
  var hit=shape.clip(eye,point,BlockPos.ZERO);assertNotNull(hit);assertEquals(Direction.DOWN,hit.getDirection());assertEquals(.8125,hit.getLocation().y,1e-8);
 }
 @Test void topSlabUsesItsRealLowerSurface(){
  var shape=Blocks.OAK_SLAB.defaultBlockState().setValue(BlockStateProperties.SLAB_TYPE,SlabType.TOP).getShape(EmptyBlockGetter.INSTANCE,BlockPos.ZERO);
  var hit=shape.clip(new Vec3(.5,-2,.5),BlockFaceTarget.points(shape,Direction.DOWN).getFirst(),BlockPos.ZERO);
  assertNotNull(hit);assertEquals(.5,hit.getLocation().y,1e-8);assertEquals(Direction.DOWN,hit.getDirection());
 }
 @Test void openTrapdoorsAndFullBlocksKeepAllVisibleFaces(){
  for(var shape:new VoxelShape[]{Shapes.block(),Blocks.OAK_TRAPDOOR.defaultBlockState().setValue(BlockStateProperties.OPEN,true).getShape(EmptyBlockGetter.INSTANCE,BlockPos.ZERO)}){
   for(var face:Direction.values()){
    var point=BlockFaceTarget.points(shape,face).getFirst();var eye=point.add(face.getStepX()*3,face.getStepY()*3,face.getStepZ()*3);
    var hit=shape.clip(eye,point,BlockPos.ZERO);assertNotNull(hit);assertEquals(face,hit.getDirection());
    var checked=shape.clip(eye,BlockFaceTarget.inside(hit),BlockPos.ZERO);assertNotNull(checked);assertEquals(face,checked.getDirection());
   }
  }
 }
 @Test void multipartShapesKeepCandidatesInsideActualGeometryAndEmptyHasNone(){
  var shape=Shapes.or(Shapes.box(0,0,0,1,.5,1),Shapes.box(0,.5,.5,1,1,1));
  for(var p:BlockFaceTarget.points(shape,Direction.UP))assertTrue(shape.toAabbs().stream().anyMatch(b->b.contains(p)));
  assertTrue(BlockFaceTarget.points(Shapes.empty(),Direction.DOWN).isEmpty());
 }
 @Test void obstacleOrWrongPlacementFaceIsNotAValidInteraction(){
  var hit=new BlockHitResult(new Vec3(.5,1,.5),Direction.UP,BlockPos.ZERO,false);
  assertTrue(BlockFaceTarget.matches(hit,BlockPos.ZERO,Direction.UP));
  assertTrue(BlockFaceTarget.matches(hit,BlockPos.ZERO,null));
  assertFalse(BlockFaceTarget.matches(hit,new BlockPos(0,1,0),Direction.UP));
  assertFalse(BlockFaceTarget.matches(hit,BlockPos.ZERO,Direction.DOWN));
  assertFalse(BlockFaceTarget.matches(null,BlockPos.ZERO,Direction.UP));
 }
}
