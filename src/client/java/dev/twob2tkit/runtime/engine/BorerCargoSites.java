package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import java.util.*;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Pose;

/** Candidate geometry only; the live caller still checks placement, ray and round-trip clearance. */
final class BorerCargoSites {
	static List<Pose> stances(BlockPos chest) {
		List<Pose> result = new ArrayList<>();
		// The chest may be suspended over the original shaft: use it from underneath, not through it.
		for (int dy : new int[]{-3, -2}) result.add(BorerCargoRouting.pose(chest.getX() + .5, chest.getY() + dy + .05, chest.getZ() + .5));
		for (var side : net.minecraft.core.Direction.Plane.HORIZONTAL) for (int dy : new int[]{0, 1, -1, -2, -3}) {
			BlockPos p = chest.relative(side);
			result.add(BorerCargoRouting.pose(p.getX() + .5, chest.getY() + dy + .05, p.getZ() + .5));
		}
		return result;
	}
	static List<BlockPos> columns(BlockPos min, BlockPos max, Pose player, boolean discard) {
		List<BlockPos> result = new ArrayList<>();
		for (int x = min.getX() - 4; x <= max.getX() + 4; x++) for (int z = min.getZ() - 4; z <= max.getZ() + 4; z++) {
			if (discard && !BorerCargoPolicy.outside(x, z, min.getX(), min.getZ(), max.getX(), max.getZ())) continue;
			result.add(new BlockPos(x, 0, z));
		}
		result.sort(Comparator.comparingInt((BlockPos p) -> edge(p, min, max) ? 0 : 1)
			.thenComparingDouble(p -> Math.abs(p.getX() + .5 - player.x()) + Math.abs(p.getZ() + .5 - player.z())));
		return result;
	}
	private static boolean edge(BlockPos p, BlockPos min, BlockPos max) {
		return p.getX() <= min.getX() || p.getX() >= max.getX() || p.getZ() <= min.getZ() || p.getZ() >= max.getZ();
	}
	static List<Integer> heights(Pose p, BlockPos min, BlockPos max, int worldMin, int worldMax, Collection<BlockPos> known) {
		Set<Integer> ys = new HashSet<>();
		for (int centre : new int[]{(int)Math.floor(p.y()), min.getY(), max.getY() + 1}) addHeights(ys, centre, worldMin, worldMax);
		for (BlockPos chest : known) addHeights(ys, chest.getY(), worldMin, worldMax);
		return ys.stream().sorted(Comparator.comparingDouble(y -> Math.abs(y - p.y()))).toList();
	}
	private static void addHeights(Set<Integer> ys, int centre, int min, int max) {
		for (int y = Math.max(min + 1, centre - 8); y <= Math.min(max - 4, centre + 8); y++) ys.add(y);
	}
	private BorerCargoSites() {}
}
