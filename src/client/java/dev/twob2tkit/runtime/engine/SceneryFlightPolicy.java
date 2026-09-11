package dev.twob2tkit.runtime.engine;

/** Small motion commands, with no forward input until the terrain clearance has been gained. */
final class SceneryFlightPolicy {
	static final double CLEARANCE = 48, MAX_Y = 512;
	record Input(float yaw, boolean forward, boolean up, double speed) {}
	static double altitude(double current, int highestSurface, double previous) {
		return Math.max(Math.max(current, previous), Math.max(160, highestSurface + CLEARANCE));
	}
	static Input input(double dx, double dz, double dy, double vy, float yaw) {
		if (dy > 1.0) return new Input(yaw, false, true, dy > 5 ? .16 : .025);
		if (Math.abs(vy) > .08) return new Input(yaw, false, false, 0);
		double distance = Math.hypot(dx, dz);
		return distance < 1.5 ? new Input(yaw, false, false, 0)
			: new Input((float)Math.toDegrees(Math.atan2(-dx, dz)), true, false, distance > 8 ? .06 : .015);
	}
	private SceneryFlightPolicy() {}
}
