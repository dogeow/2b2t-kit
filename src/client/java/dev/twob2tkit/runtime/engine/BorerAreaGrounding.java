package dev.twob2tkit.runtime.engine;

/** Only a shallow, stationary work plane with a confirmed full floor can use natural grounding. */
final class BorerAreaGrounding {
	static boolean allowed(boolean horizontal, double feetY, int bottomY, double vx, double vy, double vz, boolean supported) {
		return horizontal && supported && feetY >= bottomY - .02 && feetY <= bottomY + .12
			&& Math.abs(vx) < .025 && Math.abs(vz) < .025 && Math.abs(vy) < .085;
	}
	private BorerAreaGrounding() {}
}
