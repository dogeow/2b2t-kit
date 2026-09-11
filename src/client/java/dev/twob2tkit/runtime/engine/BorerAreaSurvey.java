package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import java.util.Arrays;

/** Bounded, stationary, two-pass survey of loaded blocks; never treats a missing chunk as air. */
final class BorerAreaSurvey {
	static final int READS_PER_TICK = 2048;
	private final BlockPos min, max;
	private final int width, columns, height;
	private final boolean[] firstAir, secondAir, loaded;
	private final int[][] surfaceY;
	private final BorerAreaPlan.Cell[][] surfaceCell;
	private int pass, column, layer;

	BorerAreaSurvey(BlockPos min, BlockPos max) {
		this.min = min; this.max = max;
		width = max.getX() - min.getX() + 1;
		columns = width * (max.getZ() - min.getZ() + 1);
		height = max.getY() - min.getY() + 1;
		firstAir = new boolean[columns]; secondAir = new boolean[columns]; loaded = new boolean[columns];
		surfaceY = new int[2][columns]; surfaceCell = new BorerAreaPlan.Cell[2][columns];
		Arrays.fill(firstAir, true); Arrays.fill(secondAir, true); Arrays.fill(loaded, true);
	}

	boolean step(BorerAreaPlan.World world) {
		// End a pass on a tick boundary: the two confirmations must be separate world observations.
		for (int reads = 0; reads < READS_PER_TICK && pass < 2; reads++) {
			int y = max.getY() - layer;
			BorerAreaPlan.Cell cell = world.cell(new BlockPos(min.getX() + column % width, y, min.getZ() + column / width));
			if (cell != BorerAreaPlan.Cell.AIR) {
				(pass == 0 ? firstAir : secondAir)[column] = false;
				if (surfaceCell[pass][column] == null) { surfaceCell[pass][column] = cell; surfaceY[pass][column] = y; }
			}
			if (cell == BorerAreaPlan.Cell.UNLOADED) loaded[column] = false;
			if (++layer == height) {
				layer = 0;
				if (++column == columns) { column = 0; pass++; break; }
			}
		}
		return pass == 2;
	}
	int progress() { return (pass * columns + column) * height + layer; }
	int totalReads() { return 2 * columns * height; }
	int columns() { return columns; }
	BlockPos column(int i) { return new BlockPos(min.getX() + i % width, 0, min.getZ() + i / width); }
	boolean clear(int i) { return loaded[i] && firstAir[i] && secondAir[i]; }
	boolean loaded(int i) { return loaded[i]; }
	Integer bedrockSurface(int i) {
		return loaded[i] && surfaceCell[0][i] == BorerAreaPlan.Cell.BEDROCK
			&& surfaceCell[1][i] == BorerAreaPlan.Cell.BEDROCK && surfaceY[0][i] == surfaceY[1][i]
			? surfaceY[0][i] : null;
	}
}
