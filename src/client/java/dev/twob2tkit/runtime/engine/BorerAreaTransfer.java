package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.Cell;

/** Actual remaining surface along the same X-then-Z route used by the controller. */
final class BorerAreaTransfer {
	record Surface(boolean loaded, int y) {}
	static Surface top(BorerAreaPlan.World world, BlockPos column, int bottom, int top) {
		for (int y = top; y >= bottom; y--) {
			Cell cell = world.cell(new BlockPos(column.getX(), y, column.getZ()));
			if (cell == Cell.UNLOADED) return new Surface(false, y);
			if (cell != Cell.AIR) return new Surface(true, y);
		}
		return new Surface(true, bottom - 1);
	}
	static Surface routeTop(BorerAreaPlan.World world, BlockPos from, BlockPos to, int bottom, int top) {
		int x = from.getX(), z = from.getZ(), highest = bottom - 1;
		while (true) {
			Surface surface = top(world, new BlockPos(x, 0, z), bottom, top);
			if (!surface.loaded) return surface;
			highest = Math.max(highest, surface.y);
			if (x != to.getX()) x += Integer.signum(to.getX() - x);
			else if (z != to.getZ()) z += Integer.signum(to.getZ() - z);
			else return new Surface(true, highest);
		}
	}
	private BorerAreaTransfer() {}
}
