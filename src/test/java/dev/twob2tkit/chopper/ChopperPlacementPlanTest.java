package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChopperPlacementPlanTest {
    @Test void replaceableLeafLitterBelowCannotRedirectThePlatformDownOneBlock() {
        var target=new BlockPos(12,86,21);
        var hit=ChopperPlacementPlan.choose(target,h->h.getBlockPos().equals(target.below())
            ?target.below():h.getBlockPos().equals(target.above())?target:null);
        assertNotNull(hit);
        assertEquals(target.above(),hit.getBlockPos());
    }
    @Test void isolatedAirTargetUsesItsOwnCellWithoutReplacingNearbyVegetation() {
        var target=new BlockPos(12,86,21);
        var hit=ChopperPlacementPlan.choose(target,h->h.getBlockPos());
        assertNotNull(hit);assertEquals(target,hit.getBlockPos());
    }
    @Test void unresolvedDestinationRefusesThePlacement() {
        assertNull(ChopperPlacementPlan.choose(BlockPos.ZERO,h->BlockPos.ZERO.below()));
    }
}
