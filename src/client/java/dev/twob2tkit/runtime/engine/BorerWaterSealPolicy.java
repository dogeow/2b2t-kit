package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;

/** Bounded placement/observation transaction: never mine or walk while a seal is unconfirmed. */
final class BorerWaterSealPolicy {
	enum Action { PLACE, WAIT, DONE, FAIL }
	private int ticks, attempts, stable;
	Action step(boolean water, boolean expectedStone, boolean reachable, boolean supplies) {
		ticks++;
		if (expectedStone) {
			stable++;
			return stable >= 6 && ticks >= 12 ? Action.DONE : Action.WAIT;
		}
		stable = 0;
		if (!water || !reachable || !supplies || ticks > 90) return Action.FAIL;
		if (ticks == 1 || ticks == 31 || ticks == 61) { attempts++; return Action.PLACE; }
		return Action.WAIT;
	}
	int attempts() { return attempts; }
	static boolean sideCell(BlockPos barrier, BlockPos water, BlockPos body) {
		return water.getY() == barrier.getY() && Math.abs(water.getX() - barrier.getX()) + Math.abs(water.getZ() - barrier.getZ()) == 1
			&& (water.getX() != body.getX() || water.getZ() != body.getZ());
	}
}
