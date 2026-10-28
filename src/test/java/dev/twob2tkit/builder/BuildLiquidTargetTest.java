package dev.twob2tkit.builder;

import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BuildLiquidTargetTest {
    @BeforeAll static void bootstrap(){SharedConstants.tryDetectVersion();Bootstrap.bootStrap();}
    @Test void genericPrinterDoesNotChooseBucketStationsThatCanFloodTheOperator(){
        assertFalse(ProjectionBuildJob.automaticPlacementAllowed(Blocks.WATER.defaultBlockState()));
        assertFalse(ProjectionBuildJob.automaticPlacementAllowed(Blocks.LAVA.defaultBlockState()));
        assertTrue(dev.twob2tkit.automation.PrinterLiquidPolicy.allowed(false,Blocks.WATER.defaultBlockState()));
        assertFalse(dev.twob2tkit.automation.PrinterLiquidPolicy.allowed(true,null));
        assertTrue(ProjectionBuildJob.automaticPlacementAllowed(Blocks.DROPPER.defaultBlockState()));
        assertTrue(ProjectionBuildJob.automaticPlacementAllowed(Blocks.COBBLESTONE_SLAB.defaultBlockState()
            .setValue(BlockStateProperties.WATERLOGGED,true)));
    }
}
