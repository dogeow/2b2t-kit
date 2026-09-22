package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerOreClearanceTest {
	@Test void liveUpperQuartzCanClearTheVerifiedBlockImmediatelyBelowIt() {
		var ore = new BlockPos(95164, 70, 99665);
		var obstruction = new BlockPos(95164, 69, 99665);
		assertTrue(BorerCenterPolicy.isOffCorridorWall(95163, 99666, obstruction.getX(), obstruction.getZ(), 1, 0, 0, 1, 1));
		assertTrue(BorerMiningPolicy.allowAdjacentOreClearance(true, obstruction.distManhattan(ore), true, true));
	}
	@Test void nearbyUnrelatedWallsAndUnsupportedMiningRemainRejected() {
		assertFalse(BorerMiningPolicy.allowAdjacentOreClearance(true, 1, false, true));
		assertFalse(BorerMiningPolicy.allowAdjacentOreClearance(true, 1, true, false));
		assertFalse(BorerMiningPolicy.allowAdjacentOreClearance(false, 1, true, true));
		assertFalse(BorerMiningPolicy.allowAdjacentOreClearance(true, 2, true, true));
		assertFalse(BorerMiningPolicy.allowAdjacentOreClearance(true, 0, true, true));
	}
}
