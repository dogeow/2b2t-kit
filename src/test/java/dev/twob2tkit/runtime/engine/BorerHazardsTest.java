package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.AABB;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class BorerHazardsTest {
	@Test void adjacentGravelCannotResetMiningTargetWhenItsFallColumnMissesPlayer() {
		AABB player = new AABB(10.45, 70, 20.15, 11.05, 71.8, 20.75);
		assertFalse(BorerHazards.fallingColumnIntersectsPlayer(player, new BlockPos(10, 73, 19)));
		assertTrue(BorerHazards.fallingColumnIntersectsPlayer(player, new BlockPos(10, 73, 20)));
	}

	@Test void nearBoundaryStillProtectsPlayerWithSmallSafetyMargin() {
		AABB player = new AABB(10.2, 70, 20.03, 10.8, 71.8, 20.63);
		assertTrue(BorerHazards.fallingColumnIntersectsPlayer(player, new BlockPos(10, 73, 19)));
	}
}
