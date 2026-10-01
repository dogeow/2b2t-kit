package dev.twob2tkit.automation;

import java.lang.reflect.Proxy;
import java.util.Map;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.SpawnPlacements;
import net.minecraft.world.level.LevelReader;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.level.border.WorldBorder;
import net.minecraft.world.phys.shapes.BooleanOp;
import net.minecraft.world.phys.shapes.Shapes;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LightSurveyPolicyTest {
    private static final BlockPos FLOOR=BlockPos.ZERO;
    @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    private LevelReader world(Map<BlockPos,BlockState> blocks){
        return (LevelReader)Proxy.newProxyInstance(LevelReader.class.getClassLoader(),new Class<?>[]{LevelReader.class},
            (proxy,method,args)->switch(method.getName()){
                case "getWorldBorder"->new WorldBorder();
                case "getBlockState"->blocks.getOrDefault((BlockPos)args[0],Blocks.AIR.defaultBlockState());
                default->throw new AssertionError("Unexpected world query:"+method.getName());
            });
    }
    private boolean zombieGeometry(Map<BlockPos,BlockState> blocks){
        var level=world(blocks);var feet=FLOOR.above();
        if(!SpawnPlacements.isSpawnPositionOk(EntityType.ZOMBIE,level,feet))return false;
        var body=EntityType.ZOMBIE.getDimensions().makeBoundingBox(feet.getX()+.5,feet.getY(),feet.getZ()+.5);
        for(var row:blocks.entrySet()){
            var pos=row.getKey();var shape=row.getValue().getCollisionShape(level,pos).move(pos.getX(),pos.getY(),pos.getZ());
            if(Shapes.joinIsNotEmpty(shape,Shapes.create(body),BooleanOp.AND))return false;
        }
        return true;
    }
    @Test void readingsArePreservedAndFootLightGovernsLightingRisk(){
        var s=LightSurveyPolicy.sample(0,0,14,0,true,0);
        assertEquals(0,s.blockLight());assertEquals(14,s.spawnBlockLight());
        assertTrue(s.zombieSpawnFloor());assertFalse(s.zombieBlockLightRisk());
    }
    @Test void zeroFootBlockLightIsRiskEvenIfDaylightCurrentlyReachesTheFloor(){
        var s=LightSurveyPolicy.sample(0,15,0,15,true,0);
        assertTrue(s.zombieBlockLightRisk()); // Darkness later can change the sky test; no spawn-now claim.
    }
    @Test void invalidFloorAndDimensionBlockLightLimitStayDistinct(){
        assertFalse(LightSurveyPolicy.sample(0,0,0,0,false,0).zombieBlockLightRisk());
        assertTrue(LightSurveyPolicy.sample(0,0,7,0,true,7).zombieBlockLightRisk());
        assertFalse(LightSurveyPolicy.sample(0,0,8,0,true,7).zombieBlockLightRisk());
    }
    @Test void outOfRangeLightIsNotSilentlyClampedOrInvented(){
        for(int v:new int[]{-1,16}){
            assertThrows(IllegalArgumentException.class,()->LightSurveyPolicy.sample(v,0,0,0,true,0));
            assertThrows(IllegalArgumentException.class,()->LightSurveyPolicy.sample(0,v,0,0,true,0));
            assertThrows(IllegalArgumentException.class,()->LightSurveyPolicy.sample(0,0,v,0,true,0));
            assertThrows(IllegalArgumentException.class,()->LightSurveyPolicy.sample(0,0,0,v,true,0));
        }
    }
    @Test void actualVanillaFloorPredicateRejectsGlassAndLeavesDespiteFullCollisionCube(){
        var glass=Blocks.GLASS.defaultBlockState();var leaves=Blocks.OAK_LEAVES.defaultBlockState();
        assertTrue(glass.isCollisionShapeFullBlock(world(Map.of(FLOOR,glass)),FLOOR));
        assertFalse(zombieGeometry(Map.of(FLOOR,glass)));
        assertFalse(zombieGeometry(Map.of(FLOOR,leaves)));
        assertTrue(zombieGeometry(Map.of(FLOOR,Blocks.STONE.defaultBlockState())));
    }
    @Test void topAndBottomSlabsUseRealSpawnSurfaceRules(){
        var slab=Blocks.STONE_SLAB.defaultBlockState();
        assertTrue(zombieGeometry(Map.of(FLOOR,slab.setValue(BlockStateProperties.SLAB_TYPE,SlabType.TOP))));
        assertFalse(zombieGeometry(Map.of(FLOOR,slab.setValue(BlockStateProperties.SLAB_TYPE,SlabType.BOTTOM))));
    }
    @Test void realSpawnSpaceRejectsWaterAndHeadCeiling(){
        var stone=Blocks.STONE.defaultBlockState();
        assertFalse(zombieGeometry(Map.of(FLOOR,stone,FLOOR.above(),Blocks.WATER.defaultBlockState())));
        assertFalse(zombieGeometry(Map.of(FLOOR,stone,FLOOR.above(2),stone)));
    }
    @Test void partialCollisionInBodySpaceDoesNotBecomeASpawnableFloor(){
        assertFalse(zombieGeometry(Map.of(FLOOR,Blocks.STONE.defaultBlockState(),FLOOR.above(),Blocks.WHITE_CARPET.defaultBlockState())));
    }
}
