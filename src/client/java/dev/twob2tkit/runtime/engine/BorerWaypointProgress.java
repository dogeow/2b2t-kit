package dev.twob2tkit.runtime.engine;

import java.util.HashSet;
import java.util.Set;
import net.minecraft.core.BlockPos;

/** Replanning through the same cells is not new progress toward the same goal. */
final class BorerWaypointProgress {
	private final Set<BlockPos> visited = new HashSet<>();
	private long count;
	boolean visit(BlockPos point) {
		if (!visited.add(point.immutable())) return false;
		count++; return true;
	}
	long count() { return count; }
	void resetTarget() { visited.clear(); }
}
