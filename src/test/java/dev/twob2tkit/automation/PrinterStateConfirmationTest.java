package dev.twob2tkit.automation;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.StairsShape;
import net.minecraft.core.Direction;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PrinterStateConfirmationTest {
 @Test void dryWaterloggablePlacementIsAnIntermediateWithoutCompletingTheWetGoal(){
  var dry=Blocks.SPRUCE_TRAPDOOR.defaultBlockState();
  var wet=dry.setValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.WATERLOGGED,true);
  assertEquals(dry,PrinterStateConfirmation.placementExpectation(wet,dry));
  assertFalse(PrinterStateConfirmation.matches(wet,dry));
  assertTrue(PrinterStateConfirmation.matches(dry,dry));
  var wrongFacing=dry.setValue(TrapDoorBlock.FACING,Direction.EAST);
  assertEquals(wet,PrinterStateConfirmation.placementExpectation(wet,wrongFacing));
  assertEquals(dry,PrinterStateConfirmation.placementExpectation(dry,wet));
  var batch=new PrinterBatchCompletion<String,net.minecraft.world.level.block.state.BlockState>();
  batch.begin(java.util.List.of("cell"));batch.acknowledge("cell",wet,true,true,false);
  assertFalse(batch.complete(java.util.Set.of("cell")));
 }
 @Test void doubleSlabFirstHalfIsOnlyAnIntermediatePlacementAck(){
  var goal=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(SlabBlock.TYPE,net.minecraft.world.level.block.state.properties.SlabType.DOUBLE);
  for(var half:java.util.List.of(net.minecraft.world.level.block.state.properties.SlabType.BOTTOM,net.minecraft.world.level.block.state.properties.SlabType.TOP)){
   var predicted=goal.setValue(SlabBlock.TYPE,half);
   assertEquals(predicted,PrinterStateConfirmation.placementExpectation(goal,predicted));
   assertTrue(PrinterStateConfirmation.matches(predicted,predicted));
   assertFalse(PrinterStateConfirmation.matches(goal,predicted));
   assertEquals(goal,PrinterStateConfirmation.placementExpectation(goal,predicted.setValue(SlabBlock.WATERLOGGED,true)));
  }
  assertEquals(goal,PrinterStateConfirmation.placementExpectation(goal,Blocks.STONE_SLAB.defaultBlockState()));
  var bottom=Blocks.COBBLESTONE_SLAB.defaultBlockState();
  assertEquals(bottom,PrinterStateConfirmation.placementExpectation(bottom,bottom.setValue(SlabBlock.TYPE,net.minecraft.world.level.block.state.properties.SlabType.TOP)));
  assertEquals(goal,PrinterStateConfirmation.placementExpectation(goal,goal));
 }
 @Test void wireConnectionsCanChangeWhileItsNeighborsAreStillBeingBuilt(){
  var expected=Blocks.REDSTONE_WIRE.defaultBlockState().setValue(RedStoneWireBlock.EAST,net.minecraft.world.level.block.state.properties.RedstoneSide.SIDE);
  var actual=expected.setValue(RedStoneWireBlock.EAST,net.minecraft.world.level.block.state.properties.RedstoneSide.NONE);
  assertTrue(PrinterStateConfirmation.matches(expected,actual));assertNotEquals(expected,actual);
  assertFalse(PrinterStateConfirmation.matches(expected,actual.setValue(RedStoneWireBlock.POWER,15)));
  assertFalse(PrinterStateConfirmation.matches(expected,Blocks.TRIPWIRE.defaultBlockState()));
 }
 @Test void aPotMustBeAcknowledgedBeforeItsSeparatePlantFill(){
  var goal=Blocks.POTTED_FERN.defaultBlockState();var empty=Blocks.FLOWER_POT.defaultBlockState();
  assertEquals(empty,PrinterStateConfirmation.placementExpectation(goal,empty));
  assertFalse(PrinterStateConfirmation.matches(goal,empty));
  assertEquals(goal,PrinterStateConfirmation.placementExpectation(goal,goal));
  assertEquals(goal,PrinterStateConfirmation.placementExpectation(goal,Blocks.DIRT.defaultBlockState()));
 }
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 @Test void fenceCanBeAcknowledgedBeforeItsNextNeighborIsBuilt(){
  var expected=Blocks.OAK_FENCE.defaultBlockState().setValue(FenceBlock.EAST,true);var actual=Blocks.OAK_FENCE.defaultBlockState();
  assertTrue(PrinterStateConfirmation.matches(expected,actual));assertNotEquals(expected,actual);
 }
 @Test void neighborStairShapeDoesNotHideWrongFacing(){
  var expected=Blocks.DEEPSLATE_TILE_STAIRS.defaultBlockState().setValue(StairBlock.SHAPE,StairsShape.INNER_LEFT);
  assertTrue(PrinterStateConfirmation.matches(expected,expected.setValue(StairBlock.SHAPE,StairsShape.STRAIGHT)));
  assertFalse(PrinterStateConfirmation.matches(expected,expected.setValue(StairBlock.FACING,Direction.SOUTH)));
 }
 @Test void leafDistanceMayChangeUntilNeighboringLogsArePlaced(){
  var expected=Blocks.OAK_LEAVES.defaultBlockState().setValue(LeavesBlock.DISTANCE,3).setValue(LeavesBlock.PERSISTENT,true);
  var observed=expected.setValue(LeavesBlock.DISTANCE,5);
  assertTrue(PrinterStateConfirmation.matches(expected,observed));
  assertNotEquals(expected,observed);
  assertFalse(PrinterStateConfirmation.matches(expected,observed.setValue(LeavesBlock.PERSISTENT,false)));
  var natural=Blocks.OAK_LEAVES.defaultBlockState().setValue(LeavesBlock.DISTANCE,3);
  assertFalse(PrinterStateConfirmation.matches(natural,natural.setValue(LeavesBlock.DISTANCE,5)));
 }
 @Test void aWrongMaterialNeverCountsAsConfirmation(){assertFalse(PrinterStateConfirmation.matches(Blocks.BARREL.defaultBlockState(),Blocks.OAK_PLANKS.defaultBlockState()));}
 @Test void knownPlaceThenInteractStepsCanBeConfirmedWithoutAcceptingWrongOrientation(){
  var open=Blocks.OAK_TRAPDOOR.defaultBlockState().setValue(TrapDoorBlock.OPEN,true);var closed=open.setValue(TrapDoorBlock.OPEN,false);
  assertEquals(closed,PrinterStateConfirmation.placementExpectation(open,closed));
  var west=Blocks.BARREL.defaultBlockState().setValue(BarrelBlock.FACING,Direction.WEST);
  assertEquals(west,PrinterStateConfirmation.placementExpectation(west,west.setValue(BarrelBlock.FACING,Direction.EAST)));
  var stripped=Blocks.STRIPPED_SPRUCE_LOG.defaultBlockState();var raw=Blocks.SPRUCE_LOG.defaultBlockState();
  assertEquals(raw,PrinterStateConfirmation.placementExpectation(stripped,raw));
  assertEquals(stripped,PrinterStateConfirmation.placementExpectation(stripped,raw.setValue(RotatedPillarBlock.AXIS,Direction.Axis.X)));
 }
}
