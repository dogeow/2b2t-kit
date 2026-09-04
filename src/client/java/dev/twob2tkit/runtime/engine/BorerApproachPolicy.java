package dev.twob2tkit.runtime.engine;

/**
 * 够不着时飞向目标方块，不要沿通道朝向按 W。
 * 来源：382821 飞着朝东走近，目标却在西下一格，距离 4.1 / 可挖 3.9。
 */
final class BorerApproachPolicy {
	private BorerApproachPolicy() {
	}

	/** 理论圈外：走近目标本身，不要沿巷道前进。 */
	static boolean approachTargetInsteadOfCorridor(boolean inRange) {
		return !inRange;
	}

	/** 水平距离仍大时按住前进。 */
	static boolean holdForward(double horiz) {
		return horiz > 0.35;
	}

	/** 目标明显更低时下降。 */
	static boolean descend(double destY, double playerY) {
		return destY + 1.0 < playerY;
	}

	/** 目标明显更高时上升。 */
	static boolean ascend(double destY, double playerY) {
		return destY > playerY + 1.2;
	}

	/** 已在飞或高低差够大时开飞行。 */
	static boolean enableFlight(boolean alreadyFlying, double destY, double playerY) {
		return alreadyFlying || Math.abs(destY - playerY) >= 2.0;
	}

	/** 同一列、目标在脚下：关掉乱飞，下落靠近。 */
	static boolean dropDownSameColumn(boolean sameColumn, boolean destBelow) {
		return sameColumn && destBelow;
	}

	/** 区域挖够不着/打偏时不要沿巷道按 W。 */
	static boolean walkCorridorWhenTooFar(boolean areaMode) {
		return !areaMode;
	}
}
