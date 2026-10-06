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
    @Test void mutationAndWitnessBoundsRemainFiniteAndContainTheRequestedRoot(){
        assertTrue(plan.contains(root));assertFalse(plan.contains(root.below()));assertFalse(plan.contains(null));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,root.above(),root.above(4)));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,root,root.offset(65,0,0)));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,root,root.offset(64,127,64)));
        assertThrows(IllegalArgumentException.class,()->new ChopperFixedTreePlan(root,null,root));
    }
}
