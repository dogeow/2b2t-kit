package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

/**
 * 锁住 2026-11-12 下界 94836 25 99519 烫伤：挖石英 94836 26 99518 时六面没贴岩浆，
 * 但北侧空腔 94836 26 99517 连着岩浆 94836 26 99516，挖穿后岩浆沿空腔流进通道。
 */
class LavaSeepPolicyTest {
	private static LavaSeepPolicy.Cell at(Map<BlockPos, LavaSeepPolicy.Cell> world, BlockPos pos) {
		return world.getOrDefault(pos, LavaSeepPolicy.Cell.SOLID);
	}

	@Test
	void lavaBehindAdjacentAirPocketIsFound() {
		Map<BlockPos, LavaSeepPolicy.Cell> world = new HashMap<>();
		world.put(new BlockPos(94836, 26, 99517), LavaSeepPolicy.Cell.OPEN);
		world.put(new BlockPos(94836, 25, 99517), LavaSeepPolicy.Cell.OPEN);
		world.put(new BlockPos(94836, 26, 99516), LavaSeepPolicy.Cell.LAVA);
		BlockPos target = new BlockPos(94836, 26, 99518);
		assertEquals(new BlockPos(94836, 26, 99516),
			LavaSeepPolicy.upstreamLava(target, pos -> at(world, pos), LavaSeepPolicy.MAX_OPEN_STEPS));
	}

	@Test
	void lavaFallingFromAboveThePocketIsFound() {
		Map<BlockPos, LavaSeepPolicy.Cell> world = new HashMap<>();
		world.put(new BlockPos(0, 26, -1), LavaSeepPolicy.Cell.OPEN);
		world.put(new BlockPos(0, 27, -1), LavaSeepPolicy.Cell.OPEN);
		world.put(new BlockPos(0, 28, -1), LavaSeepPolicy.Cell.LAVA);
		assertEquals(new BlockPos(0, 28, -1),
			LavaSeepPolicy.upstreamLava(new BlockPos(0, 26, 0), pos -> at(world, pos), LavaSeepPolicy.MAX_OPEN_STEPS));
	}

	@Test
	void lavaBelowThePocketCannotFlowUpIntoTheTunnel() {
		Map<BlockPos, LavaSeepPolicy.Cell> world = new HashMap<>();
		world.put(new BlockPos(0, 26, -1), LavaSeepPolicy.Cell.OPEN);
		world.put(new BlockPos(0, 25, -1), LavaSeepPolicy.Cell.LAVA);
		assertNull(LavaSeepPolicy.upstreamLava(new BlockPos(0, 26, 0), pos -> at(world, pos), LavaSeepPolicy.MAX_OPEN_STEPS));
	}

	@Test
	void lavaSealedBySolidRockOrBeyondTheStepLimitIsIgnored() {
		Map<BlockPos, LavaSeepPolicy.Cell> world = new HashMap<>();
		world.put(new BlockPos(0, 26, -2), LavaSeepPolicy.Cell.LAVA); // 中间是实心石头
		assertNull(LavaSeepPolicy.upstreamLava(new BlockPos(0, 26, 0), pos -> at(world, pos), 3));

		Map<BlockPos, LavaSeepPolicy.Cell> far = new HashMap<>();
		for (int z = -1; z >= -4; z--) far.put(new BlockPos(0, 26, z), LavaSeepPolicy.Cell.OPEN);
		far.put(new BlockPos(0, 26, -5), LavaSeepPolicy.Cell.LAVA);
		assertNull(LavaSeepPolicy.upstreamLava(new BlockPos(0, 26, 0), pos -> at(far, pos), 3));
	}
}
