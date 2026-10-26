package dev.twob2tkit.automation;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.SlabBlock;
import net.minecraft.world.level.block.state.properties.SlabType;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
class PrinterSlabPlacementTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 @Test void sideSeedHitsTheAnchorsOccupiedHalfInsteadOfMergingTheAnchor(){
  var anchor=new BlockPos(4,72,8);var goal=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(SlabBlock.TYPE,SlabType.DOUBLE);
  for(var face:List.of(Direction.NORTH,Direction.SOUTH,Direction.WEST,Direction.EAST))for(var half:List.of(SlabType.BOTTOM,SlabType.TOP)){
   var hit=PrinterSlabPlacement.sideHit(goal,Blocks.AIR.defaultBlockState(),goal.setValue(SlabBlock.TYPE,half),anchor.relative(face),anchor,face);
   assertEquals(anchor,hit.getBlockPos());assertEquals(face,hit.getDirection());
   assertEquals(half==SlabType.BOTTOM?72.25:72.75,hit.getLocation().y);
   assertEquals(anchor.getX()+.5+face.getStepX()*.5,hit.getLocation().x);
   assertEquals(anchor.getZ()+.5+face.getStepZ()*.5,hit.getLocation().z);
  }
 }
 @Test void correctionNeverExtendsToAnotherMaterialOrWetOrOccupiedTargets(){
  var anchor=new BlockPos(4,72,8);var target=anchor.east();var bottom=Blocks.COBBLESTONE_SLAB.defaultBlockState();var goal=bottom.setValue(SlabBlock.TYPE,SlabType.DOUBLE);var air=Blocks.AIR.defaultBlockState();
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.sideHit(goal,air,Blocks.STONE_SLAB.defaultBlockState(),target,anchor,Direction.EAST));
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.sideHit(goal,air,bottom.setValue(SlabBlock.WATERLOGGED,true),target,anchor,Direction.EAST));
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.sideHit(goal,bottom,bottom,target,anchor,Direction.EAST));
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.sideHit(goal,air,goal,target,anchor,Direction.EAST));
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.sideHit(goal,air,bottom,target.east(),anchor,Direction.EAST));
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.sideHit(bottom,air,bottom,target,anchor,Direction.EAST));
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.sideHit(goal,air,bottom,anchor.above(),anchor,Direction.UP));
 }
 @Test void theSecondUseMergesTheTargetItselfRatherThanAnotherAnchor(){
  var target=new BlockPos(4,72,8);var bottom=Blocks.COBBLESTONE_SLAB.defaultBlockState();var goal=bottom.setValue(SlabBlock.TYPE,SlabType.DOUBLE);
  for(var half:List.of(SlabType.BOTTOM,SlabType.TOP)){
   var hit=PrinterSlabPlacement.placementHit(goal,bottom.setValue(SlabBlock.TYPE,half),Blocks.STONE.defaultBlockState(),target,target.north(),Direction.SOUTH);
   assertEquals(target,hit.getBlockPos());assertEquals(half==SlabType.BOTTOM?Direction.UP:Direction.DOWN,hit.getDirection());
   assertEquals(72.5,hit.getLocation().y);
  }
  assertThrows(IllegalArgumentException.class,()->PrinterSlabPlacement.placementHit(goal,bottom.setValue(SlabBlock.WATERLOGGED,true),bottom,target,target.north(),Direction.SOUTH));
 }
 public static final class Action {public final Object context;Action(Object c){context=c;}}
 @Test void prepareAndInteractShareExactlyTheSameCorrectedContext()throws Exception{
  Object before=new Object(),after=new Object();var prepare=new Action(before);var interact=new Action(before);
  assertEquals(2,PrinterSlabPlacement.replaceContexts(List.of(prepare,interact,new Object()),before,after));
  assertSame(after,prepare.context);assertSame(after,interact.context);
 }
 @Test void anUnknownActionQueueFailsBeforeItCanBeRun(){
  Object before=new Object();assertThrows(IllegalStateException.class,()->PrinterSlabPlacement.replaceContexts(List.of(new Action(before)),before,new Object()));
 }
}
