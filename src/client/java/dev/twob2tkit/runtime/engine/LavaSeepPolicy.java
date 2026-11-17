package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;

import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.function.Function;

/**
 * 挖开一格后，岩浆能否经旁边已有的空腔流进来。
 * 只看六面邻接会漏掉「目标 → 空气口袋 → 岩浆」：挖穿后口袋与通道连通，岩浆顺着流进脚下。
 * 岩浆只会从上方或水平方向流入，所以只沿这几个方向往上游找。
 */
final class LavaSeepPolicy {
	/** 往上游穿过的空气格上限：够覆盖贴着通道的小空腔，又不至于把远处洞穴都算进来。 */
	static final int MAX_OPEN_STEPS = 3;

	private static final Direction[] UPSTREAM = {
		Direction.UP, Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST
	};

	enum Cell { LAVA, OPEN, SOLID }

	private LavaSeepPolicy() {
	}

	/** 目标挖开后能流进来的岩浆格；没有则 null。目标自身的六面邻接由调用方另查。 */
	static BlockPos upstreamLava(BlockPos target, Function<BlockPos, Cell> cellAt, int maxOpenSteps) {
		ArrayDeque<BlockPos> queue = new ArrayDeque<>();
		ArrayDeque<Integer> depths = new ArrayDeque<>();
		HashSet<BlockPos> visited = new HashSet<>();
		BlockPos start = target.immutable();
		visited.add(start);
		queue.add(start);
		depths.add(0);
		while (!queue.isEmpty()) {
			BlockPos cell = queue.removeFirst();
			int depth = depths.removeFirst();
			for (Direction direction : UPSTREAM) {
				BlockPos next = cell.relative(direction).immutable();
				if (!visited.add(next)) continue;
				Cell kind = cellAt.apply(next);
				if (kind == Cell.LAVA) return next;
				if (kind == Cell.OPEN && depth < maxOpenSteps) {
					queue.add(next);
					depths.add(depth + 1);
				}
			}
		}
		return null;
	}
}
