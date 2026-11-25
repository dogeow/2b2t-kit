package dev.twob2tkit.structure;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class EndCityHeightTest {
    private static final long SEED = 1009504104802950675L;

    @BeforeAll static void bootstrapVanillaRegistries() {
        net.minecraft.SharedConstants.tryDetectVersion();
        net.minecraft.server.Bootstrap.bootStrap();
    }

    /** 4519,-54937 地面只有 58 格；旧的岛噪声线性估高会把它列成末地城。 */
    @Test void lowIslandIsNotListedAsCity() {
        assertEquals(58, StructureLocator.endIslandSurfaceY(SEED, 4519, -54937));
        assertFalse(StructureLocator.canPlaceEndCity(SEED, 4519 >> 4, -54937 >> 4));
        var hits = StructureLocator.nearby(SEED, 4519, -54937, StructureLocator.Kind.END_CITY, 6000, 1000, null);
        assertFalse(hits.isEmpty());
        assertTrue(hits.stream().noneMatch(hit -> hit.x() == 4519 && hit.z() == -54937));
        assertTrue(hits.stream().noneMatch(hit -> hit.x() == 4903 && hit.z() == -55017));
    }

    /** has_structure/end_city 含 end_midlands；Chunkbase 在这三处都标了城，旧代码只认高地会漏掉。 */
    @Test void midlandsCitiesAreListed() {
        var hits = StructureLocator.nearby(SEED, 1580, 53, StructureLocator.Kind.END_CITY, 2500, 1000, null);
        for (int[] site : new int[][]{{1063,343},{3255,-233},{3287,-1209}})
            assertTrue(hits.stream().anyMatch(hit -> hit.x() == site[0] && hit.z() == site[1]), site[0] + "," + site[1]);
    }

    /** 由近到远分批求值、够数即停：大半径的前几项必须和小半径一致。 */
    @Test void earlyStopKeepsTheNearestCandidatesInOrder() {
        var near = StructureLocator.nearby(SEED, 4519, -54937, StructureLocator.Kind.END_CITY, 6000, 1000, null);
        var far = StructureLocator.nearby(SEED, 4519, -54937, StructureLocator.Kind.END_CITY, 16000, 20, null);
        assertEquals(near.subList(0, 20), far);
    }
}
