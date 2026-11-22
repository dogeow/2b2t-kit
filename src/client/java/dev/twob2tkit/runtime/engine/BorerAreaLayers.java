package dev.twob2tkit.runtime.engine;

import java.util.function.IntPredicate;

/**
 * Tall areas above sea level are cleared standing up: fixed 4-high slabs from the selection top down,
 * each run as a shallow horizontal plan whose floor is the next slab. Slabs with nothing to dig are skipped.
 * The grid is anchored at the selection top so a checkpointed slab is found again after a restart.
 */
final class BorerAreaLayers {
	static final int HEIGHT = 4;

	private BorerAreaLayers() {}

	/** Above sea level and too tall for one shallow pass; at or below the water line the shaft strategy stays. */
	static boolean standing(int bottom, int top, int seaLevel) {
		return !BorerAreaHorizontal.enabled(new net.minecraft.core.BlockPos(0, bottom, 0), new net.minecraft.core.BlockPos(0, top, 0))
			&& top >= bottom && bottom >= seaLevel - 1;
	}

	static int count(int bottom, int top) {
		return (top - bottom + HEIGHT) / HEIGHT;
	}

	static int top(int top, int index) {
		return top - index * HEIGHT;
	}

	static int bottom(int bottom, int top, int index) {
		return Math.max(bottom, top(top, index) - HEIGHT + 1);
	}

	/** First slab at or after {@code from} that still has work, or -1 when the whole area is clear. */
	static int firstWithWork(int from, int bottom, int top, IntPredicate hasWork) {
		for (int index = Math.max(0, from); index < count(bottom, top); index++) if (hasWork.test(index)) return index;
		return -1;
	}
}
