package dev.twob2tkit.runtime.engine;

/** Maps a planner command to the exact yaw and keys used by the live runner. */
final class BorerAreaMotion {
	static final double MAX_HORIZONTAL_SPEED = .08;
	record Input(float yaw, boolean forward, boolean up, boolean down, double speed) {}
	static Input of(BorerAreaPlan.Command c, BorerAreaPlan.Pose p, float yaw) {
		double error;
		switch (c.action()) {
			case X -> {
				error = c.x() - p.x();
				double speed = horizontalSpeed(error,p.vx());
				return new Input(error > 0 ? -90 : 90, speed > 0, false, false, speed);
			}
			case Z -> {
				error = c.z() - p.z();
				double speed = horizontalSpeed(error,p.vz());
				return new Input(error > 0 ? 0 : 180, speed > 0, false, false, speed);
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
	static double horizontalSpeed(double error, double velocity) {
		double remaining = Math.max(0,Math.abs(error)-Math.max(0,Math.signum(error)*velocity));
		return Math.min(MAX_HORIZONTAL_SPEED,remaining/30.0);
	}
	static double horizontalProbe(double error, double velocity) {
		return Math.min(Math.abs(error),Math.max(.25,Math.abs(velocity)+horizontalSpeed(error,velocity)*15));
	}
	private static double verticalSpeed(double error, double vy) {
		double remaining = Math.max(0, Math.abs(error) - Math.max(0, Math.signum(error) * vy));
		return remaining > 4 ? 0.20 : remaining > 0.8 ? 0.08 : Math.min(0.025, remaining / 10.0);
	}
	private BorerAreaMotion() {}
}
