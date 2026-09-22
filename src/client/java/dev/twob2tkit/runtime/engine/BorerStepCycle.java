package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;

/** Detect repeated one-block rises followed by a return to the same footprint. */
final class BorerStepCycle {
	private BlockPos step;
	private double x, y, z;
	private boolean raised;
	private int returns;
	void reset() { step = null; raised = false; returns = 0; }
	void madeProgress() { reset(); }
	void begin(BlockPos next, double px, double py, double pz) {
		if (next.equals(step)) return;
		reset(); step = next.immutable(); x = px; y = py; z = pz;
	}
	boolean observe(double px, double py, double pz) {
		if (step == null) return false;
		if (Math.hypot(px - x, pz - z) >= .8) { reset(); return false; }
		if (py >= y + .7) raised = true;
		if (raised && py <= y + .2) { raised = false; returns++; }
		return returns >= 2;
	}
}
