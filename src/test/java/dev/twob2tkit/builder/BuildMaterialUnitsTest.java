package dev.twob2tkit.builder;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.*;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BuildMaterialUnitsTest {
 @BeforeAll static void bootstrap(){SharedConstants.tryDetectVersion();Bootstrap.bootStrap();}
 @Test void stateWorkDoesNotDemandAnotherCopyOfTheBlock(){
  var dry=Blocks.SPRUCE_TRAPDOOR.defaultBlockState();var wet=dry.setValue(BlockStateProperties.WATERLOGGED,true);
  assertEquals(0,ProjectionBuildJob.materialUnits(wet,dry));
  assertEquals(1,ProjectionBuildJob.materialUnits(wet,Blocks.AIR.defaultBlockState()));
  assertEquals(1,ProjectionBuildJob.materialUnits(wet,Blocks.DIRT.defaultBlockState()));
  var slab=Blocks.COBBLESTONE_SLAB.defaultBlockState();
  assertEquals(1,ProjectionBuildJob.materialUnits(slab.setValue(BlockStateProperties.SLAB_TYPE,SlabType.DOUBLE),slab));
  assertEquals(0,ProjectionBuildJob.materialUnits(slab,slab));
 }
}
