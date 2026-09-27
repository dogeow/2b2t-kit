package dev.twob2tkit.builder;

import net.minecraft.core.BlockPos;
import net.minecraft.SharedConstants;
import net.minecraft.server.Bootstrap;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BuildStartStationSearchTest {
    @BeforeAll static void bootstrap(){SharedConstants.tryDetectVersion();Bootstrap.bootStrap();}

    @Test void startSearchIncludesNearbyCorridorPositionsButStaysBounded(){
        var center=new BlockPos(100,70,-40);
        var candidates=ProjectionBuildJob.startCandidates(center);
        assertEquals(245,candidates.size());
        assertTrue(candidates.contains(center));
        assertTrue(candidates.contains(center.offset(3,0,-3)));
        assertFalse(candidates.contains(center.offset(4,0,0)));
        assertFalse(candidates.contains(center.offset(0,3,0)));
    }
}
