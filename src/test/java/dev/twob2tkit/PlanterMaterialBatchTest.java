package dev.twob2tkit;

import dev.twob2tkit.planter.PlanterMaterialBatch;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class PlanterMaterialBatchTest {
    @BeforeAll static void bootstrap() {
        net.minecraft.SharedConstants.tryDetectVersion(); net.minecraft.server.Bootstrap.bootStrap();
    }
    @Test void predictedAirAndDuplicateUsesCannotCompleteOrRepeatTheBatch() {
        var soil=new BlockPos(0,63,0);var crop=soil.above();
        var batch=new PlanterMaterialBatch(List.of(soil),3);
        batch.serverBlock(crop,Blocks.AIR.defaultBlockState(),true);
        assertFalse(batch.mayPlant(crop));
        batch.harvestSent(crop);
        assertThrows(IllegalStateException.class,()->batch.harvestSent(crop));
        assertThrows(IllegalStateException.class,()->batch.plantSent(crop));
        batch.serverBlock(crop,Blocks.AIR.defaultBlockState(),false);
        assertFalse(batch.mayPlant(crop));assertFalse(batch.done(4,5));
        batch.serverBlock(crop,Blocks.AIR.defaultBlockState(),true);
        batch.plantSent(crop);
        assertThrows(IllegalStateException.class,()->batch.plantSent(crop));
        batch.serverBlock(crop,Blocks.WHEAT.defaultBlockState(),false);
        assertFalse(batch.done(4,5));
        batch.serverBlock(crop,Blocks.WHEAT.defaultBlockState(),true);
        assertFalse(batch.done(3,5));assertFalse(batch.done(4,3));assertTrue(batch.done(4,4));
        assertTrue(batch.currentCrops(List.of(Blocks.WHEAT.defaultBlockState())));
        assertFalse(batch.currentCrops(List.of(Blocks.AIR.defaultBlockState())));
    }
    @Test void outsideCropPacketsAndDifferentPlantsCannotAcknowledgeTheExplicitVisit() {
        var soil=new BlockPos(0,63,0);var batch=new PlanterMaterialBatch(List.of(soil),0);
        batch.harvestSent(soil.above());
        batch.serverBlock(soil.above().east(),Blocks.AIR.defaultBlockState(),true);
        assertFalse(batch.mayPlant(soil.above()));
        batch.serverBlock(soil.above(),Blocks.AIR.defaultBlockState(),true);batch.plantSent(soil.above());
        batch.serverBlock(soil.above(),Blocks.CARROTS.defaultBlockState(),true);
        assertFalse(batch.done(1,4));
    }
    @Test void explicitVisitRejectsEmptyDuplicateAndOversizedFields() {
        assertThrows(IllegalArgumentException.class,()->new PlanterMaterialBatch(List.of(),0));
        var soil=new BlockPos(0,63,0);
        assertThrows(IllegalArgumentException.class,()->new PlanterMaterialBatch(List.of(soil,soil),0));
        assertThrows(IllegalArgumentException.class,()->new PlanterMaterialBatch(
            java.util.stream.IntStream.range(0,17).mapToObj(x->new BlockPos(x,63,0)).toList(),0));
    }
}
