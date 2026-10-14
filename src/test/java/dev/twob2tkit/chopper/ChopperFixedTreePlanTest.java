package dev.twob2tkit.chopper;

import java.util.List;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChopperFixedTreePlanTest {
    private final BlockPos root=new BlockPos(761033,69,797882);
    private final ChopperFixedTreePlan plan=new ChopperFixedTreePlan(root,root.offset(-8,0,-8),root.offset(8,22,8));
    @Test void exactOwnedTreeAcceptsItsCrownAndRefusesAnAdjacentIndependentTree(){
        assertTrue(plan.accepts(List.of(root,root.above(6),root.offset(0,5,-5)),List.of(root),"minecraft:cherry_log"));
        assertFalse(plan.accepts(List.of(root),List.of(root.offset(2,0,0)),"minecraft:cherry_log"));
        assertFalse(plan.accepts(List.of(root,root.offset(2,0,0)),List.of(root,root.offset(2,0,0)),"minecraft:cherry_log"));
        assertFalse(plan.accepts(List.of(root,root.offset(9,4,0)),List.of(root),"minecraft:cherry_log"));
    }
    @Test void aBrokenRootCannotBeReplacedWithTheRemainingCrownOrAnotherTree(){
        assertFalse(plan.accepts(List.of(root.above(5)),List.of(),"minecraft:cherry_log"));
        assertFalse(plan.accepts(List.of(root.offset(1,0,0)),List.of(root.offset(1,0,0)),"minecraft:cherry_log"));
        assertFalse(plan.accepts(List.of(),List.of(root),"minecraft:cherry_log"));
    }
    @Test void wideSpeciesAllowOnlyTheirSelectedTwoByTwoRootFootprint(){
        var roots=List.of(root,root.offset(1,0,0),root.offset(0,0,1),root.offset(1,0,1));
        assertTrue(plan.accepts(roots,roots,"minecraft:dark_oak_log"));
        assertFalse(plan.accepts(roots,roots,"minecraft:cherry_log"));
        assertFalse(plan.accepts(roots,List.of(root,root.offset(2,0,0)),"minecraft:spruce_log"));
    }
    @Test void standbyExcludesFullBodyAndWideRoots(){
        assertTrue(plan.outsideFutureTrunk(761032.5,797882.5,"minecraft:cherry_log"));
        assertFalse(plan.outsideFutureTrunk(761033.7044,797882.8637,"minecraft:cherry_log"));
        assertFalse(plan.outsideFutureTrunk(761032.8,797882.5,"minecraft:cherry_log"));
        assertFalse(plan.outsideFutureTrunk(Double.NaN,797882.5,"minecraft:cherry_log"));
        assertFalse(plan.outsideFutureTrunk(761032.5,797882.5,"minecraft:dark_oak_log"));
        assertTrue(plan.outsideFutureTrunk(761031.5,797882.5,"minecraft:dark_oak_log"));
    }
    @Test void aCurrentNaturalWideTreeCanHaveOneTerrainStepAcrossItsFourStumps(){
        var selected=new BlockPos(759383,85,796210);
        var natural=new ChopperFixedTreePlan(selected,selected.offset(-11,-5,-11),selected.offset(11,39,11));
        var stumps=List.of(selected,new BlockPos(759382,84,796209),
            new BlockPos(759382,85,796210),new BlockPos(759383,84,796209));
        assertTrue(natural.accepts(stumps,stumps,"minecraft:dark_oak_log"));
        assertFalse(natural.accepts(stumps,stumps,"minecraft:cherry_log"));
        assertFalse(natural.accepts(stumps,List.of(selected,selected.offset(-1,-2,-1)),"minecraft:dark_oak_log"));
    }
    @Test void aWideRootStillCannotSpanThreeColumnsOrOppositeHeightSteps(){
        var local=new ChopperFixedTreePlan(root,root.offset(-11,-5,-11),root.offset(11,39,11));
        var tooWide=List.of(root,root.offset(-1,0,0),root.offset(1,0,0));
        assertFalse(local.accepts(tooWide,tooWide,"minecraft:dark_oak_log"));
        var tooTall=List.of(root,root.offset(1,-1,0),root.offset(0,1,1));
        assertFalse(local.accepts(tooTall,tooTall,"minecraft:dark_oak_log"));
    }
    @Test void mutationAndWitnessBoundsRemainFiniteAndContainTheRequestedRoot(){
        assertTrue(plan.contains(root));assertFalse(plan.contains(root.below()));assertFalse(plan.contains(null));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,root.above(),root.above(4)));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,root,root.offset(65,0,0)));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,root,root.offset(64,127,64)));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,null,root));
    }
}
