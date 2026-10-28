package dev.twob2tkit.runtime.engine;
import dev.twob2tkit.runtime.api.BuildNavigation;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeAll;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class NavigationHazardClearanceTest {
    @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    private NavigationHazardClearance.Cells cells(Set<BlockPos> hot,Set<BlockPos> missing) {
        return new NavigationHazardClearance.Cells(){
            public boolean loaded(BlockPos p){return !missing.contains(p);}
            public boolean hazardous(BlockPos p){return hot.contains(p);}
        };
    }
    @Test void airBodyDoesNotAuthorizeLavaFloorOrAdjacentContact() {
        var feet=new BlockPos(0,1,0);
        assertFalse(NavigationHazardClearance.safe(feet,cells(Set.of(BlockPos.ZERO),Set.of())));
        assertFalse(NavigationHazardClearance.safe(feet,cells(Set.of(new BlockPos(1,0,1)),Set.of())));
        assertTrue(NavigationHazardClearance.safe(feet,cells(Set.of(new BlockPos(2,0,0)),Set.of())));
    }
    @Test void unobservedSurroundingCellIsNotClearance() {
        assertFalse(NavigationHazardClearance.safe(new BlockPos(0,1,0),cells(Set.of(),Set.of(new BlockPos(1,0,1)))));
    }
    @Test void extinguishedCampfireIsDifferentFromBurningCampfire() {
        assertFalse(NavigationHazardClearance.hazardous("minecraft:campfire",false));
        assertTrue(NavigationHazardClearance.hazardous("minecraft:campfire",true));
        assertTrue(NavigationHazardClearance.hazardous("minecraft:magma_block",false));
    }
    @Test void directShortcutAndGridSearchBothHonorInjectedSafety() {
        var denied=new BlockPos(1,0,0);
        var nav=new DefaultBuildNavigation(p->!p.equals(denied));
        var world=new BuildNavigation.World(){
            public boolean clear(BlockPos p){return p.getY()==0&&p.getX()>=0&&p.getX()<=2&&p.getZ()>=0&&p.getZ()<=1;}
            public boolean edge(BlockPos a,BlockPos b){return true;}
        };
        var search=nav.search(world,BlockPos.ZERO,List.of(new BlockPos(2,0,0)));
        BuildNavigation.Result result=null;
        while(result==null)result=search.advance(16,Long.MAX_VALUE);
        assertFalse(result.nodes().isEmpty());assertFalse(result.nodes().contains(denied));
        assertTrue(result.nodes().size()>2,"The direct leg through the denied cell must not be shortcut");
    }
    @Test void exposedHotBlockThreeBelowIsNotALowHoverStationButHigherReachRemainsAvailable(){
        var magma=new BlockPos(0,61,0);
        assertFalse(NavigationHazardClearance.safe(new BlockPos(0,64,0),cells(Set.of(magma),Set.of())));
        assertFalse(NavigationHazardClearance.safe(new BlockPos(0,64,0),cells(Set.of(magma.offset(1,0,1)),Set.of())));
        assertTrue(NavigationHazardClearance.safe(new BlockPos(0,65,0),cells(Set.of(magma),Set.of())));
        var stations=new DefaultBuildNavigation(p->true).stations(new BlockPos(0,62,0));
        assertTrue(stations.contains(new BlockPos(0,65,0)));
        assertFalse(stations.contains(new BlockPos(1,65,0)),"Higher station still obeys actual eye reach");
    }
    @Test void completedFloorCanShieldLowerHeatWithoutIgnoringContactOrUnknownCells(){
        var feet=new BlockPos(0,64,0);var magma=feet.below(3);
        var shielded=new NavigationHazardClearance.Cells(){
            public boolean loaded(BlockPos p){return true;}
            public boolean hazardous(BlockPos p){return p.equals(magma);}
            public boolean barrier(BlockPos p){return p.equals(feet.below(2));}
        };
        assertTrue(NavigationHazardClearance.safe(feet,shielded));
        assertFalse(NavigationHazardClearance.safe(feet,cells(Set.of(feet.below()),Set.of())));
        assertFalse(NavigationHazardClearance.safe(feet,cells(Set.of(),Set.of(feet.below(3)))));
    }
    @Test void onlyDryFullOrTopSlabFloorsAreHeatBarriers(){
        var level=net.minecraft.world.level.EmptyBlockGetter.INSTANCE;var p=BlockPos.ZERO;
        var slab=net.minecraft.world.level.block.Blocks.COBBLESTONE_SLAB.defaultBlockState();
        assertTrue(NavigationHazardClearance.barrier(net.minecraft.world.level.block.Blocks.COBBLESTONE.defaultBlockState(),level,p));
        assertFalse(NavigationHazardClearance.barrier(slab,level,p));
        slab=slab.setValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.SLAB_TYPE,
            net.minecraft.world.level.block.state.properties.SlabType.TOP);
        assertTrue(NavigationHazardClearance.barrier(slab,level,p));
        assertFalse(NavigationHazardClearance.barrier(slab.setValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.WATERLOGGED,true),level,p));
        assertFalse(NavigationHazardClearance.barrier(net.minecraft.world.level.block.Blocks.CHEST.defaultBlockState(),level,p));
    }
}
