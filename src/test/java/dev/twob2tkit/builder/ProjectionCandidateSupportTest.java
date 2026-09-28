package dev.twob2tkit.builder;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.CropBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.material.Fluids;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;

import static org.junit.jupiter.api.Assertions.*;

class ProjectionCandidateSupportTest {
    private static final BlockPos TARGET=new BlockPos(761007,64,797848);

    @BeforeAll static void bootstrap(){
        net.minecraft.SharedConstants.tryDetectVersion();
        net.minecraft.server.Bootstrap.bootStrap();
    }

    private static LevelReader world(BlockState ground,BlockState target){
        return (LevelReader)Proxy.newProxyInstance(LevelReader.class.getClassLoader(),new Class<?>[]{LevelReader.class},(proxy,method,args)->switch(method.getName()){
            case "getBlockState" -> {
                var pos=(BlockPos)args[0];
                yield pos.equals(TARGET)?target:pos.equals(TARGET.below())?ground:Blocks.AIR.defaultBlockState();
            }
            case "getRawBrightness","getMaxLocalRawBrightness" -> 15;
            case "getFluidState" -> Fluids.EMPTY.defaultFluidState();
            default -> throw new AssertionError("Unexpected world query: "+method.getName());
        });
    }

    @Test void maturePotatoesNeedActualFarmlandBeforeTheyBecomeConstructionTargets(){
        var potato=Blocks.POTATOES.defaultBlockState().setValue(CropBlock.AGE,7);
        var air=Blocks.AIR.defaultBlockState();
        // Isolated JUnit has no datapack tags, so exercise the exact live-soil
        // gate separately from the vanilla canSurvive call it precedes.
        assertFalse(ProjectionBuildJob.cropSoilReady(potato,Blocks.GRASS_BLOCK.defaultBlockState()));
        assertTrue(ProjectionBuildJob.cropSoilReady(potato,Blocks.FARMLAND.defaultBlockState()));
        assertFalse(ProjectionBuildJob.liveTargetReady(potato,world(Blocks.GRASS_BLOCK.defaultBlockState(),air),TARGET));
    }

    @Test void ordinaryBlocksRemainReadyAndOccupiedTargetsStayExcluded(){
        var stone=Blocks.STONE_BRICKS.defaultBlockState();
        var grass=Blocks.GRASS_BLOCK.defaultBlockState();
        assertTrue(ProjectionBuildJob.liveTargetReady(stone,world(grass,Blocks.AIR.defaultBlockState()),TARGET));
        assertFalse(ProjectionBuildJob.liveTargetReady(stone,world(grass,Blocks.TORCH.defaultBlockState()),TARGET));
    }
}
