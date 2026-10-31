package dev.twob2tkit.automation;
import java.util.*;
import net.minecraft.core.*;
import net.minecraft.world.level.*;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.*;
import net.minecraft.world.level.block.entity.BlockEntity;
import net.minecraft.world.level.material.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
class ModelWaterPlanTest {
 @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 static class Grid implements BlockGetter {
  final Map<BlockPos,BlockState> rows=new HashMap<>();public BlockEntity getBlockEntity(BlockPos p){return null;}
  public BlockState getBlockState(BlockPos p){return rows.getOrDefault(p,Blocks.AIR.defaultBlockState());}
  public FluidState getFluidState(BlockPos p){return getBlockState(p).getFluidState();}public int getHeight(){return 384;}public int getMinY(){return -64;}
 }
 final BlockPos source=new BlockPos(0,68,0);final ProjectedWaterFlowPolicy.Bounds bounds=new ProjectedWaterFlowPolicy.Bounds(new ProjectedWaterFlowPolicy.Cell(-9,67,-9),new ProjectedWaterFlowPolicy.Cell(9,69,9));
 Grid[] channel(int length,BlockState floor){
  var actual=new Grid();var goal=new Grid();
  for(int i=0;i<length;i++){
   var p=source.north(i);goal.rows.put(p,Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,i));
   for(var grid:List.of(actual,goal)){grid.rows.put(p.below(),floor);grid.rows.put(p.east(),Blocks.GLASS.defaultBlockState());grid.rows.put(p.west(),Blocks.GLASS.defaultBlockState());}
  }
  for(var grid:List.of(actual,goal)){grid.rows.put(source.south(),Blocks.GLASS.defaultBlockState());grid.rows.put(source.north(length),Blocks.GLASS.defaultBlockState());}
  return new Grid[]{actual,goal};
 }
 String reject(Grid[] g){return ModelWaterPlan.rejection(g[0],g[1],bounds,source,p->false);}
 @Test void originalShortAndLongChannelsAllowOnlyTheirOriginalSource(){for(int n:new int[]{2,3,5,8})assertNull(reject(channel(n,Blocks.COBBLESTONE.defaultBlockState())));}
 @Test void hopperWorkingEnabledBitDoesNotTurnAFluidBarrierIntoAnError(){
  var g=channel(5,Blocks.HOPPER.defaultBlockState());for(var p:new ArrayList<>(g[0].rows.keySet()))if(g[0].getBlockState(p).is(Blocks.HOPPER))g[0].rows.put(p,g[0].getBlockState(p).setValue(HopperBlock.ENABLED,false));assertNull(reject(g));
  g[0].rows.put(source.below(),Blocks.HOPPER.defaultBlockState().setValue(HopperBlock.FACING,Direction.EAST));assertNotNull(reject(g));
 }
 @Test void missingFloorAndTemporaryNaturalPlugCannotAuthorizeWater(){
  var g=channel(5,Blocks.COBBLESTONE.defaultBlockState());g[0].rows.remove(source.north(2).below());assertNotNull(reject(g));g=channel(5,Blocks.COBBLESTONE.defaultBlockState());g[0].rows.put(source.north(2),Blocks.DIRT.defaultBlockState());assertNotNull(reject(g));
 }
 @Test void waterMustNotEscapeTheOriginalNetwork(){var g=channel(5,Blocks.COBBLESTONE.defaultBlockState());g[0].rows.remove(source.east());g[1].rows.remove(source.east());assertNotNull(reject(g));}
 @Test void aNewSourceMustNotRegenerateIntoAnOriginalDrySlab(){
  var g=channel(2,Blocks.COBBLESTONE.defaultBlockState());var edge=source.east();var other=edge.east();var slab=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(BlockStateProperties.SLAB_TYPE,SlabType.TOP);
  for(var grid:g){grid.rows.put(edge,slab);grid.rows.put(edge.below(),Blocks.COBBLESTONE.defaultBlockState());grid.rows.put(other,Blocks.WATER.defaultBlockState());grid.rows.put(other.below(),Blocks.COBBLESTONE.defaultBlockState());}
  assertTrue(reject(g).contains("regeneration"));
 }
 @Test void aSourceAtTheDeclaredEdgeAndRegenerationJustAcrossTheEdgeAreRejected(){
  var g=channel(2,Blocks.COBBLESTONE.defaultBlockState());var edgeBounds=new ProjectedWaterFlowPolicy.Bounds(new ProjectedWaterFlowPolicy.Cell(0,67,-9),new ProjectedWaterFlowPolicy.Cell(9,69,9));assertNotNull(ModelWaterPlan.rejection(g[0],g[1],edgeBounds,source,p->false));
  var narrow=new ProjectedWaterFlowPolicy.Bounds(new ProjectedWaterFlowPolicy.Cell(-1,67,-2),new ProjectedWaterFlowPolicy.Cell(1,69,1));var edge=source.east();var beyond=edge.east();
  for(var grid:g){grid.rows.put(edge,Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(BlockStateProperties.SLAB_TYPE,SlabType.TOP));grid.rows.put(edge.below(),Blocks.COBBLESTONE.defaultBlockState());grid.rows.put(beyond,Blocks.WATER.defaultBlockState());}
  assertNotNull(ModelWaterPlan.rejection(g[0],g[1],narrow,source,p->false));
 }
 @Test void campfireAndDryStairFloorsRemainOriginalFluidBarriers(){assertNull(reject(channel(3,Blocks.SOUL_CAMPFIRE.defaultBlockState())));assertNull(reject(channel(3,Blocks.COBBLESTONE_STAIRS.defaultBlockState())));}
 @Test void bubbleTargetsAndLivingEntitiesRequireTheirOwnHandling(){var g=channel(2,Blocks.MAGMA_BLOCK.defaultBlockState());assertNotNull(reject(g));g=channel(2,Blocks.COBBLESTONE.defaultBlockState());assertNotNull(ModelWaterPlan.rejection(g[0],g[1],bounds,source,p->p.equals(source.north())));}
 @Test void closeVisibleUnsupportedOrAngryThreatsAreNeverCoveredByTheOccludedProof(){
  assertTrue(ModelWaterThreatPolicy.permit("minecraft:zombie",true,false,100,false));assertFalse(ModelWaterThreatPolicy.permit("minecraft:zombie",true,false,63,false));
  assertTrue(ModelWaterThreatPolicy.permit("minecraft:skeleton",true,false,150,false));assertFalse(ModelWaterThreatPolicy.permit("minecraft:skeleton",true,false,143,false));
  assertFalse(ModelWaterThreatPolicy.permit("minecraft:skeleton",true,true,1000,false));assertFalse(ModelWaterThreatPolicy.permit("minecraft:creeper",true,false,1000,false));assertFalse(ModelWaterThreatPolicy.permit("minecraft:vex",true,false,1000,false));
  assertTrue(ModelWaterThreatPolicy.permit("minecraft:enderman",true,false,100,true));assertFalse(ModelWaterThreatPolicy.permit("minecraft:enderman",true,false,100,false));assertFalse(ModelWaterThreatPolicy.permit("minecraft:enderman",false,false,100,true));
 }
 @Test void nativeBucketAndOwnerActuallyUseTheNewScopedGuard()throws Exception{
  var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/BucketWaterAction.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}
  boolean constructed=false,checked=false;
  for(var method:node.methods)for(var i:method.instructions)if(i instanceof org.objectweb.asm.tree.MethodInsnNode c){constructed|=method.name.equals("<init>")&&c.owner.endsWith("ProjectedModelWaterGuard")&&c.name.equals("<init>");checked|=method.name.equals("boundedHole")&&c.owner.endsWith("ProjectedModelWaterGuard")&&c.name.equals("require");}
  assertTrue(constructed&&checked);
  node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}
  boolean owner=false;for(var method:node.methods)if(method.name.equals("bucketOwnerCurrent"))for(var i:method.instructions)if(i instanceof org.objectweb.asm.tree.MethodInsnNode c)owner|=c.owner.endsWith("ProjectedModelWaterGuard")&&c.name.equals("shieldedWorkspace");assertTrue(owner);
 }
 @Test void explicitFlagNeedsBoolean(){assertFalse(ProjectedModelWaterGuard.requested(new com.google.gson.JsonObject()));assertThrows(IllegalArgumentException.class,()->ProjectedModelWaterGuard.requested(com.google.gson.JsonParser.parseString("{\"projected_model_water_source\":1}").getAsJsonObject()));}
 @Test void unsentGeometryChecksStillUsePrePlacementPhase(){
  assertTrue(BucketWaterPolicy.columnRequiresAir(false,false));
  assertTrue(BucketWaterPolicy.columnRequiresAir(true,false));
  assertFalse(BucketWaterPolicy.columnRequiresAir(false,true));
  assertTrue(BucketWaterPolicy.columnRequiresAir(true,true));
  assertDoesNotThrow(()->{
   String source=java.nio.file.Files.readString(java.nio.file.Path.of("src/client/java/dev/twob2tkit/automation/BucketWaterAction.java"));
   assertTrue(source.contains("projectedModelWater.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()))"));
  });
 }
 @Test void flowCorrectionIsExplicitAndCannotTargetLegitimateSourcesOrBlocks(){
  assertFalse(ProjectedFlowCorrectionGuard.requested(new com.google.gson.JsonObject()));
  assertThrows(IllegalArgumentException.class,()->ProjectedFlowCorrectionGuard.requested(com.google.gson.JsonParser.parseString("{\"projected_flow_source_drain\":1}").getAsJsonObject()));
  for(int i=1;i<=7;i++)assertTrue(ProjectedFlowCorrectionGuard.originalFlow(Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,i)));
  assertFalse(ProjectedFlowCorrectionGuard.originalFlow(Blocks.WATER.defaultBlockState()));
  assertFalse(ProjectedFlowCorrectionGuard.originalFlow(Blocks.AIR.defaultBlockState()));
  assertFalse(ProjectedFlowCorrectionGuard.originalFlow(Blocks.BUBBLE_COLUMN.defaultBlockState()));
  assertFalse(ProjectedFlowCorrectionGuard.originalFlow(Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,8)));
  assertTrue(ProjectedFlowCorrectionGuard.currentFlowOrAir(Blocks.AIR.defaultBlockState()));
  assertFalse(ProjectedFlowCorrectionGuard.currentFlowOrAir(Blocks.LAVA.defaultBlockState()));
  assertFalse(ProjectedFlowCorrectionGuard.currentFlowOrAir(Blocks.CHEST.defaultBlockState()));
 }
 @Test void correctionGuardIsWiredIntoOwnershipAndBucketPreflight()throws Exception{
  var bridge=new org.objectweb.asm.tree.ClassNode();new org.objectweb.asm.ClassReader(AutomationBridge.class.getResourceAsStream("AutomationBridge.class")).accept(bridge,0);
  boolean owner=false,protocol=false;for(var m:bridge.methods)for(var i:m.instructions){if(i instanceof org.objectweb.asm.tree.MethodInsnNode call&&m.name.equals("bucketOwnerCurrent"))owner|=call.owner.endsWith("ProjectedFlowCorrectionGuard")&&call.name.equals("shieldedWorkspace");if(i instanceof org.objectweb.asm.tree.LdcInsnNode value)protocol|="projected_flow_source_drain_protocol".equals(value.cst);}assertTrue(owner);assertTrue(protocol);
  var bucket=new org.objectweb.asm.tree.ClassNode();new org.objectweb.asm.ClassReader(BucketWaterAction.class.getResourceAsStream("BucketWaterAction.class")).accept(bucket,0);
  boolean checked=false;for(var m:bucket.methods)if(m.name.equals("validateBeforeSend"))for(var i:m.instructions)if(i instanceof org.objectweb.asm.tree.MethodInsnNode call)checked|=call.owner.endsWith("ProjectedFlowCorrectionGuard")&&call.name.equals("require");assertTrue(checked);
 }
}
