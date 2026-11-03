package dev.twob2tkit.automation;
import net.minecraft.core.*;import net.minecraft.world.level.block.*;import net.minecraft.world.level.block.state.properties.*;import org.junit.jupiter.api.*;import static org.junit.jupiter.api.Assertions.*;
class TieredModelWaterPlanTest {
 @BeforeAll static void boot(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
 final BlockPos source=new BlockPos(0,70,0);final ProjectedWaterFlowPolicy.Bounds b=new ProjectedWaterFlowPolicy.Bounds(new ProjectedWaterFlowPolicy.Cell(-3,66,-3),new ProjectedWaterFlowPolicy.Cell(3,71,3));
 ModelWaterPlanTest.Grid[] sealed(){var a=new ModelWaterPlanTest.Grid();var m=new ModelWaterPlanTest.Grid();
  // Two levels of wet envelope; solid side walls and lower floor enclose every potential regenerated source.
  for(int x=-2;x<=2;x++)for(int z=-2;z<=2;z++)for(int y=67;y<=70;y++){
   var p=new BlockPos(x,y,z);boolean wall=Math.abs(x)==2||Math.abs(z)==2||y==67;var s=wall?Blocks.COBBLESTONE.defaultBlockState():Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,1);m.rows.put(p,s);if(wall)a.rows.put(p,s);
  }m.rows.put(source,Blocks.WATER.defaultBlockState());return new ModelWaterPlanTest.Grid[]{a,m};}
 String reject(ModelWaterPlanTest.Grid[] g){return TieredModelWaterPlan.rejection(g[0],g[1],b,source,p->false);}
 @Test void explicitlyEnclosedFallingVolumeAllowsDryAndFlowingCells(){var g=sealed();assertNull(reject(g));g[0].rows.put(source.below(),Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,8));assertNull(reject(g));}
 @Test void originalPlanarModeStillRejectsFallingGeometry(){var g=sealed();assertNotNull(ModelWaterPlan.rejection(g[0],g[1],b,source,p->false));}
 @Test void absentFloorOrWrongWallFails(){var g=sealed();g[0].rows.remove(new BlockPos(0,67,0));assertNotNull(reject(g));g=sealed();g[0].rows.put(new BlockPos(2,69,0),Blocks.DIRT.defaultBlockState());assertNotNull(reject(g));}
 @Test void modelCannotAuthorizeAnOpenEscapeOrUnboundedSource(){var g=sealed();var p=new BlockPos(2,69,0);g[0].rows.remove(p);g[1].rows.put(p,Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,1));assertNotNull(reject(g));assertFalse(TieredModelWaterPlan.bounds(new ProjectedWaterFlowPolicy.Bounds(new ProjectedWaterFlowPolicy.Cell(-3,65,-3),new ProjectedWaterFlowPolicy.Cell(3,71,3)),source));}
 @Test void wetCellsCannotDisplaceBlocksLavaOrLivingEntities(){var g=sealed();g[0].rows.put(source.below(),Blocks.DIRT.defaultBlockState());assertNotNull(reject(g));g=sealed();g[0].rows.put(source.below(),Blocks.LAVA.defaultBlockState());assertNotNull(reject(g));g=sealed();assertNotNull(TieredModelWaterPlan.rejection(g[0],g[1],b,source,p->p.equals(source.below())));}
 @Test void onlyOriginalLevelZeroTarget(){var g=sealed();g[1].rows.put(source,Blocks.WATER.defaultBlockState().setValue(LiquidBlock.LEVEL,1));assertNotNull(reject(g));}
 @Test void regenerationCannotWaterlogDryBoundary(){var g=sealed();var p=new BlockPos(0,68,0);var slab=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(SlabBlock.TYPE,SlabType.TOP);g[0].rows.put(p,slab);g[1].rows.put(p,slab);assertNotNull(reject(g));}
 @Test void bubbleFloorsNeedTheirDedicatedMode(){for(var block:new net.minecraft.world.level.block.Block[]{Blocks.MAGMA_BLOCK,Blocks.SOUL_SAND}){var g=sealed();g[0].rows.put(new BlockPos(0,67,0),block.defaultBlockState());g[1].rows.put(new BlockPos(0,67,0),block.defaultBlockState());assertNotNull(reject(g));}}
 @Test void typedOptInCannotBeEnabledByStrings(){var r=com.google.gson.JsonParser.parseString("{\"projected_model_water_source\":true,\"model_water_tiered_containment\":\"true\"}").getAsJsonObject();assertThrows(IllegalArgumentException.class,()->ProjectedModelWaterGuard.option(r,"model_water_tiered_containment"));assertFalse(ProjectedModelWaterGuard.option(com.google.gson.JsonParser.parseString("{}").getAsJsonObject(),"model_water_tiered_containment"));}
}
