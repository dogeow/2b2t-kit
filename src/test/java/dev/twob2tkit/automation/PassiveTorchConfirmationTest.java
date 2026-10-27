package dev.twob2tkit.automation;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import org.junit.jupiter.api.*;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class PassiveTorchConfirmationTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 @Test void poweredWallTorchCanAcknowledgeLitPlacementBeforeItsScheduledOffState(){
  var goal=Blocks.REDSTONE_WALL_TORCH.defaultBlockState().setValue(WallTorchBlock.FACING,Direction.SOUTH).setValue(BlockStateProperties.LIT,false);
  var initial=goal.setValue(BlockStateProperties.LIT,true);
  assertTrue(PrinterStateConfirmation.passiveTorchTransition(goal,initial));assertEquals(initial,PrinterStateConfirmation.placementExpectation(goal,initial));assertFalse(PrinterStateConfirmation.matches(goal,initial));
  assertFalse(PrinterStateConfirmation.passiveTorchTransition(goal,initial.setValue(WallTorchBlock.FACING,Direction.NORTH)));
  assertEquals(goal,PrinterStateConfirmation.placementExpectation(goal,initial.setValue(WallTorchBlock.FACING,Direction.NORTH)));
 }
 @Test void passiveEligibilityCannotApplyToDifferentBlocksOrPlayerDrivenChanges(){
  var goal=Blocks.REDSTONE_TORCH.defaultBlockState().setValue(BlockStateProperties.LIT,false);
  assertFalse(PrinterStateConfirmation.passiveTorchTransition(goal,Blocks.TORCH.defaultBlockState()));
  assertFalse(PrinterStateConfirmation.passiveTorchTransition(goal,goal));
  assertFalse(PrinterStateConfirmation.passiveTorchTransition(Blocks.CAMPFIRE.defaultBlockState(),Blocks.CAMPFIRE.defaultBlockState().setValue(BlockStateProperties.LIT,false)));
  assertFalse(PrinterStateConfirmation.passiveTorchTransition(null,goal));
 }
 @Test void onlyAnAcknowledgedUseMayAwaitItsExactPassiveFinalPacket(){
  var t=new PrinterBatchCompletion<String,String>();t.begin(Set.of("p"));
  t.serverBlock("p","off");assertFalse(t.complete(Set.of("p")));
  t.acknowledge("p","off",false,true,false,"on");t.serverBlock("p","off");assertFalse(t.complete(Set.of("p")));
  t.acknowledge("p","off",true,true,false,"on");assertFalse(t.complete(Set.of("p")));
  t.serverBlock("p","off");assertTrue(t.complete(Set.of("p")));
  t.serverBlock("p","on");assertFalse(t.complete(Set.of("p")));
 }
 @Test void aBreakOrDifferentStateInvalidatesThePassiveChain(){
  var t=new PrinterBatchCompletion<String,String>();t.begin(Set.of("p"));t.acknowledge("p","off",true,true,false,"on");
  t.serverBlock("p","air");t.serverBlock("p","off");assertFalse(t.complete(Set.of("p")));
 }
 @Test void aNewQueuedActionNeedsANewOwnAcknowledgement(){
  var t=new PrinterBatchCompletion<String,String>();t.begin(Set.of("p"));t.acknowledge("p","off",true,true,false,"on");t.queued("p");
  t.serverBlock("p","off");assertFalse(t.complete(Set.of("p")));t.acknowledge("p","off",true,true,true);assertTrue(t.complete(Set.of("p")));
 }
 @Test void defaultDoubleSlabOrOtherIntermediateStillNeedsItsSeparateFinalUse(){
  var t=new PrinterBatchCompletion<String,String>();t.begin(Set.of("p"));t.acknowledge("p","double",true,true,false);
  t.serverBlock("p","double");assertFalse(t.complete(Set.of("p")));
  t.queued("p");t.acknowledge("p","double",true,true,true);assertTrue(t.complete(Set.of("p")));
 }
}
