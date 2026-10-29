package dev.twob2tkit.automation;

import com.google.gson.JsonParser;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.SlabType;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProjectedWaterlogDrainTest {
    @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    @Test void explicitBooleanOptInIsRequired(){
        assertFalse(ProjectedWaterlogDrain.requested(JsonParser.parseString("{}").getAsJsonObject()));
        assertTrue(ProjectedWaterlogDrain.requested(JsonParser.parseString("{\"projected_waterlog_drain\":true}").getAsJsonObject()));
        for(String v:new String[]{"\"true\"","1","null","[]"})assertThrows(IllegalArgumentException.class,()->ProjectedWaterlogDrain.requested(
            JsonParser.parseString("{\"projected_waterlog_drain\":"+v+"}").getAsJsonObject()));
    }
    @Test void onlyWaterloggingChangesAndSingleSlabShapeIsPreserved(){
        var dry=Blocks.COBBLESTONE_SLAB.defaultBlockState().setValue(BlockStateProperties.SLAB_TYPE,SlabType.TOP);
        var wet=dry.setValue(BlockStateProperties.WATERLOGGED,true);
        assertTrue(ProjectedWaterlogDrain.pair(wet,dry,false));
        assertFalse(ProjectedWaterlogDrain.pair(wet,dry.setValue(BlockStateProperties.SLAB_TYPE,SlabType.BOTTOM),false));
        assertFalse(ProjectedWaterlogDrain.pair(wet,dry,true));
        assertFalse(ProjectedWaterlogDrain.pair(dry,dry,false));
        assertFalse(ProjectedWaterlogDrain.pair(wet,wet,false));
        assertFalse(ProjectedWaterlogDrain.pair(wet.setValue(BlockStateProperties.SLAB_TYPE,SlabType.DOUBLE),dry.setValue(BlockStateProperties.SLAB_TYPE,SlabType.DOUBLE),false));
    }
    @Test void trapdoorFacingHalfOpenAndPoweredCannotBeCorrectedByADrain(){
        var dry=Blocks.SPRUCE_TRAPDOOR.defaultBlockState();var wet=dry.setValue(BlockStateProperties.WATERLOGGED,true);
        assertTrue(ProjectedWaterlogDrain.pair(wet,dry,false));
        assertFalse(ProjectedWaterlogDrain.pair(wet,dry.cycle(BlockStateProperties.HORIZONTAL_FACING),false));
        assertFalse(ProjectedWaterlogDrain.pair(wet,dry.cycle(BlockStateProperties.HALF),false));
        assertFalse(ProjectedWaterlogDrain.pair(wet,dry.cycle(BlockStateProperties.OPEN),false));
        assertFalse(ProjectedWaterlogDrain.pair(wet,dry.cycle(BlockStateProperties.POWERED),false));
    }
    @Test void plainWaterAirAndContainersStayOutsideProjectedDrain(){
        assertFalse(ProjectedWaterlogDrain.pair(Blocks.WATER.defaultBlockState(),Blocks.AIR.defaultBlockState(),false));
        var chest=Blocks.CHEST.defaultBlockState();assertFalse(ProjectedWaterlogDrain.pair(chest.setValue(BlockStateProperties.WATERLOGGED,true),chest,false));
    }
    @Test void queuedActionAcceptsOriginalStateButSuccessStillNeedsIndependentDryAndInventoryReceipts(){
        var dry=Blocks.COBBLESTONE_SLAB.defaultBlockState();var wet=dry.setValue(BlockStateProperties.WATERLOGGED,true);
        assertTrue(ProjectedWaterlogDrain.currentState(wet,wet,dry));assertTrue(ProjectedWaterlogDrain.currentState(dry,wet,dry));
        assertFalse(ProjectedWaterlogDrain.currentState(Blocks.AIR.defaultBlockState(),wet,dry));
        var receipt=new BucketWaterPolicy.Receipt();assertFalse(receipt.done(true,true,true,100));receipt.sendOnce();
        receipt.block(true,true,true,dry.toString(),true,10);assertFalse(receipt.done(true,true,true,100));
        receipt.inventory(true,true,true,true,11);assertTrue(receipt.done(true,true,true,19));
        receipt.block(true,true,true,wet.toString(),false,20);assertFalse(receipt.done(true,true,true,100),"Refilled waterlogging invalidates earlier dry proof");
    }
}
