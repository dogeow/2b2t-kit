package dev.twob2tkit.runtime.engine;

/** Maps a planner command to the exact yaw and keys used by the live runner. */
final class BorerAreaMotion {
	record Input(float yaw, boolean forward, boolean up, boolean down, double speed) {}
	static Input of(BorerAreaPlan.Command c, BorerAreaPlan.Pose p, float yaw) {
		double error;
		switch (c.action()) {
			case X -> {
				error = c.x() - p.x();
				return new Input(error > 0 ? -90 : 90, true, false, false, Math.abs(error) < 0.8 ? 0.005 : 0.016);
			}
			case Z -> {
				error = c.z() - p.z();
				return new Input(error > 0 ? 0 : 180, true, false, false, Math.abs(error) < 0.8 ? 0.005 : 0.016);
			}
			case UP, DOWN -> {
				error = c.y() - p.y();
				return new Input(yaw, false, c.action() == BorerAreaPlan.Action.UP,
					c.action() == BorerAreaPlan.Action.DOWN, verticalSpeed(error, p.vy()));
			}
			case MINE_DOWN -> {
				double gap = Math.max(0, p.y() - c.y() - Math.max(0, -p.vy()));
				return new Input(yaw, false, false, gap > 0.03, Math.min(0.12, gap / 10.0));
			}
			default -> { return new Input(yaw, false, false, false, 0); }
		}
	}
	private static double verticalSpeed(double error, double vy) {
		double remaining = Math.max(0, Math.abs(error) - Math.max(0, Math.signum(error) * vy));
		return remaining > 4 ? 0.20 : remaining > 0.8 ? 0.08 : Math.min(0.025, remaining / 10.0);
	}
	private BorerAreaMotion() {}
}
