package dev.twob2tkit.chopper;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ChopperFlightSafetyTest {
    @Test void capturedStraddlingBodyWaitsForTheFreshSaplingInsteadOfCallingItDangerous() {
        // The stopped route began beside a newly planted sapling, while the player straddled four columns.
        AABB swept=new AABB(760999.648,73.440,797891.859,761000.248,75.240,797892.459)
            .expandTowards(-.2,0,0).deflate(.001);
        BlockPos sapling=new BlockPos(761000,73,797891);
        Set<BlockPos> cells=new HashSet<>();
        for(BlockPos p:BlockPos.betweenClosed(BlockPos.containing(swept.minX,swept.minY,swept.minZ),
            BlockPos.containing(swept.maxX,swept.maxY,swept.maxZ)))cells.add(p.immutable());
        assertTrue(cells.contains(sapling));
        for(int tick=0;tick<7;tick++) {
            var kind=ChopperFlightSafety.classify(true,true,true,false,false,false,false);
            assertEquals(ChopperFlightSafety.Kind.PENDING,kind);
            assertEquals(ChopperFlightSafety.Action.WAIT,ChopperFlightSafety.action(kind,tick));
        }
        var confirmed=ChopperFlightSafety.classify(true,true,false,false,false,false,false);
        assertEquals(ChopperFlightSafety.Action.MOVE,ChopperFlightSafety.action(confirmed,7));
    }
    @Test void realHazardsRemainBlockedRatherThanReceivingTheConfirmationGracePeriod() {
        for(var kind:List.of(ChopperFlightSafety.Kind.FLUID,ChopperFlightSafety.Kind.FIRE,
            ChopperFlightSafety.Kind.COBWEB,ChopperFlightSafety.Kind.POWDER_SNOW,ChopperFlightSafety.Kind.OUT_OF_WORLD))
            assertEquals(ChopperFlightSafety.Action.STOP,ChopperFlightSafety.action(kind,0));
        assertEquals(ChopperFlightSafety.Kind.FLUID,ChopperFlightSafety.classify(true,true,false,true,false,false,false));
        assertEquals(ChopperFlightSafety.Kind.FIRE,ChopperFlightSafety.classify(true,true,false,false,true,false,false));
    }
    @Test void unknownOrUnconfirmedCellsCannotWaitForeverOrAuthorizeMovement() {
        for(var kind:List.of(ChopperFlightSafety.Kind.UNLOADED,ChopperFlightSafety.Kind.PENDING)) {
            assertEquals(ChopperFlightSafety.Action.WAIT,ChopperFlightSafety.action(kind,99));
            assertEquals(ChopperFlightSafety.Action.STOP,ChopperFlightSafety.action(kind,100));
        }
    }
}
