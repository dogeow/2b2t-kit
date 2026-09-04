package dev.twob2tkit.runtime.engine;

/**
 * 按 XYZ 误差闭环走位：靠近才继续按键，冲过格心就停，越走越远就反向。
 * 精细对准时把 Meteor Flight speed 降下来。
 */
final class BorerSteerPolicy {
	static final double DEADZONE = 0.08;
	static final double PRECISE_FLIGHT_SPEED = 0.03;
	static final double SLOW_IF_FASTER_THAN = 0.06;

	private BorerSteerPolicy() {
	}

	/** 水平误差是否超出死区。 */
	static boolean needMove(double errorX, double errorZ) {
		// 按键也是逐轴用 DEADZONE；这里必须一致，否则 0.06/0.06 会报告要动却没有任何键可按。
		return Math.max(Math.abs(errorX), Math.abs(errorZ)) > DEADZONE;
	}

	/** 垂直误差是否超出死区。 */
	static boolean needMoveY(double errorY) {
		return Math.abs(errorY) > DEADZONE;
	}

	/** 误差是否变大。 */
	static boolean errorGrew(double prev, double now) {
		return Math.abs(now) > Math.abs(prev) + 0.01;
	}

	/** 误差是否越过零点。 */
	static boolean crossed(double prev, double now) {
		return prev * now < 0.0 && Math.abs(now) > 1.0e-4;
	}

	/** 冲过目标是否该刹车。 */
	static boolean shouldBrake(double prevDist, double dist, boolean havePrev) {
		return havePrev && dist > prevDist + 0.02;
	}

	/**
	 * error = 目标 - 当前。正值表示要往正方向走。
	 * @param havePrev 上一拍有记录
	 */
	static boolean pressPositive(double error, double prevError, boolean havePrev) {
		if (Math.abs(error) <= DEADZONE) return false;
		if (havePrev && crossed(prevError, error)) return false;
		boolean positive = error > 0.0;
		if (havePrev && errorGrew(prevError, error)) positive = !positive;
		return positive;
	}

	/** 是否按负向键（含冲过反向）。 */
	static boolean pressNegative(double error, double prevError, boolean havePrev) {
		if (Math.abs(error) <= DEADZONE) return false;
		if (havePrev && crossed(prevError, error)) return false;
		boolean positive = error > 0.0;
		if (havePrev && errorGrew(prevError, error)) positive = !positive;
		return !positive;
	}

	/** 精细对准是否该降 Meteor 飞速。 */
	static boolean shouldSlowFlight(double currentSpeed) {
		return currentSpeed > SLOW_IF_FASTER_THAN;
	}
}
