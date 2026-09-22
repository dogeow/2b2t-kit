package dev.twob2tkit.automation;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.StairsShape;
import net.minecraft.core.Direction;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class PrinterStateConfirmationTest {
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
