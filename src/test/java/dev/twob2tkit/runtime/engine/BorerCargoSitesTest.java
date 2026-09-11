package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class BorerCargoSitesTest {
	private final BlockPos min = new BlockPos(0, -59, 0), max = new BlockPos(15, -50, 15);
	private final BorerAreaPlan.Pose player = BorerCargoRouting.pose(8.5, -58, 8.5);
	@Test void placementIncludesBedrockFloorAndOldSurfaceBoxHeightNotJustTopSlice() {
		var ys = BorerCargoSites.heights(player, min, max, -64, 320, List.of(new BlockPos(0, 1, 0)));
		assertTrue(ys.contains(-59)); assertTrue(ys.contains(-63)); assertTrue(ys.contains(1));
		assertEquals(-58, ys.getFirst()); assertTrue(ys.stream().allMatch(y -> y >= -63 && y <= 316));
	}
	@Test void allFloorColumnsIncludingOddCoordinatesAreCandidatesAndEdgesArePreferred() {
		var columns = BorerCargoSites.columns(min, max, player, false);
		assertTrue(columns.contains(new BlockPos(7, 0, 7))); assertTrue(columns.contains(new BlockPos(1, 0, 0)));
		assertTrue(columns.getFirst().getX() == 0 || columns.getFirst().getX() == 15 || columns.getFirst().getZ() == 0 || columns.getFirst().getZ() == 15);
		assertEquals(columns.size(), new java.util.HashSet<>(columns).size());
	}
	@Test void discardOptionNeverChoosesAStandInsideTheMiningFootprint() {
		for (BlockPos p : BorerCargoSites.columns(min, max, player, true))
			assertTrue(BorerCargoPolicy.outside(p.getX(), p.getZ(), 0, 0, 15, 15));
	}
	@Test void overheadChestHasBelowAndSideStancesWithoutRequiringStandingOnTop() {
		BlockPos chest = new BlockPos(8, 1, 8);
		var stances = BorerCargoSites.stances(chest);
		assertTrue(stances.stream().anyMatch(p -> p.x() == 8.5 && p.z() == 8.5 && p.y() + 1.8 < chest.getY()));
		assertTrue(stances.stream().anyMatch(p -> p.x() != 8.5 || p.z() != 8.5));
	}
}
