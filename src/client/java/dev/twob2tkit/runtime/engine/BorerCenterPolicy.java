package dev.twob2tkit.runtime.engine;

import net.minecraft.core.Direction;
import net.minecraft.core.BlockPos;

/**
 * 1×2 通道怎么走。只改这一处。
 * <p>
 * 碰撞箱已经压到侧壁才横移回中心。用 0.06 当阈值会在两边都是石头时左右撞墙。
 * 矿就在附近更高/更低处时不要沿通道走回头。
 * 侧壁判定用选出目标时的朝向，避免找矿把朝向拧向矿后把正前方丢掉。
 * 对角接近时不要每拍在东西/南北之间切换，否则人会在格边左右横摆。
 */
public final class BorerCenterPolicy {
	/** 玩家碰撞箱半宽。偏移加上它超过 0.5 才算压到侧壁。 */
	public static final double PLAYER_HALF_WIDTH = 0.3;
	/** 宽巷对准条带中心：小于这个偏量不要左右晃。 */
	public static final double BAND_CENTER_DEADZONE = 0.12;
	/** 1×1 竖井：偏出这么多就先回到格心，否则碰撞箱卡井沿下不去。 */
	public static final double SHAFT_CENTER_DEADZONE = 0.08;

	private BorerCenterPolicy() {
	}
	/** Route clearance must use the body column; the supporting block may be across a pit edge. */
	static BlockPos navigationColumn(BlockPos body, BlockPos support, boolean ore) { return ore ? body : support; }
	static boolean centerBeforeForward(double sideOffset) { return overlapsSideWall(sideOffset); }
	static boolean reachedWaypoint(double dx, double dy, double dz) { return Math.hypot(dx, dz) <= .14 && Math.abs(dy) <= .2; }
	record WalkInput(float yaw, boolean forward, double probeX, double probeZ) {}
	static WalkInput walkInput(double dx, double dz) {
		double distance = Math.hypot(dx, dz), length = Math.max(.001, distance);
		return new WalkInput((float)(Math.toDegrees(Math.atan2(dz, dx)) - 90), distance > .06, dx / length * .22, dz / length * .22);
	}

	/**
	 * 相对格子中心、朝右为正的横向偏移。
	 * @param rightX {@code forward.getClockWise().getStepX()}
	 * @param rightZ {@code forward.getClockWise().getStepZ()}
	 */
	public static double sideOffset(double playerX, double playerZ, int feetX, int feetZ, int rightX, int rightZ) {
		double dx = feetX + 0.5 - playerX;
		double dz = feetZ + 0.5 - playerZ;
		return dx * rightX + dz * rightZ;
	}

	/** 碰撞箱已经刮到侧壁。略偏中心不要横移。 */
	public static boolean overlapsSideWall(double sideOffset) {
		return Math.abs(sideOffset) + PLAYER_HALF_WIDTH > 0.5 + 1.0e-4;
	}

	/**
	 * 相对目标点、朝右为正的横向偏移。
	 * 3 宽带要对准条带中心，不能再用当前站立格中心。
	 */
	public static double sideOffsetTo(
		double playerX, double playerZ, double targetX, double targetZ, int rightX, int rightZ
	) {
		return (targetX - playerX) * rightX + (targetZ - playerZ) * rightZ;
	}

	/** 侧偏是否大到要横移回中。 */
	public static boolean shouldStrafeToBandCenter(double sideOffset) {
		return Math.abs(sideOffset) > BAND_CENTER_DEADZONE;
	}

	/** 是否按右键朝中心收。 */
	public static boolean shouldPressRightToward(double sideOffset) {
		return sideOffset > BAND_CENTER_DEADZONE;
	}

	/** 是否按左键朝中心收。 */
	public static boolean shouldPressLeftToward(double sideOffset) {
		return sideOffset < -BAND_CENTER_DEADZONE;
	}

	/** 是否按右。 */
	public static boolean shouldPressRight(double sideOffset) {
		return overlapsSideWall(sideOffset) && sideOffset > 0;
	}

	/** 是否按左。 */
	public static boolean shouldPressLeft(double sideOffset) {
		return overlapsSideWall(sideOffset) && sideOffset < 0;
	}

	/** 相对格心的水平距离。0.2 就会卡 1×1 井沿。 */
	public static boolean needsShaftCenter(double dxToCenter, double dzToCenter) {
		return Math.hypot(dxToCenter, dzToCenter) > SHAFT_CENTER_DEADZONE;
	}

	/** 误差为负时按正向键。 */
	public static boolean pressTowardPositive(double alongOrSide) {
		return alongOrSide > SHAFT_CENTER_DEADZONE;
	}

	/** 误差为正时按负向键。 */
	public static boolean pressTowardNegative(double alongOrSide) {
		return alongOrSide < -SHAFT_CENTER_DEADZONE;
	}

	/** 1 格宽时只有正前方那一列是通道，侧向墙不是。 */
	public static boolean inCorridorColumn(int lateralAbs, int width) {
		return lateralAbs <= Math.max(0, width / 2);
	}

	/**
	 * 侧壁判定必须用选出这块时的朝向。
	 * 沿该朝向 along≥1 且在通道宽内是正前方，不是侧壁。
	 * 找矿每 tick 把朝向拧向矿之后，along=0 / lateral=1 不能用来丢掉已选的前方。
	 */
	public static boolean isOffCorridorWall(int along, int lateralAbs, int width) {
		if (along >= 1 && inCorridorColumn(lateralAbs, width)) return false;
		return !inCorridorColumn(lateralAbs, width);
	}

	/** 用目标被选中时保存的原点和朝向计算侧墙，不能混用玩家后来所在列或后来朝向。 */
	public static boolean isOffCorridorWall(
		int originX,
		int originZ,
		int targetX,
		int targetZ,
		int forwardX,
		int forwardZ,
		int rightX,
		int rightZ,
		int width
	) {
		int dx = targetX - originX;
		int dz = targetZ - originZ;
		int along = dx * forwardX + dz * forwardZ;
		int lateralAbs = Math.abs(dx * rightX + dz * rightZ);
		return isOffCorridorWall(along, lateralAbs, width);
	}

	/**
	 * 这一步会不会让到矿的水平曼哈顿距离变近。
	 * 已经到目标列、或会走远时不要走，避免手动走进去又被带出来。
	 */
	public static boolean headingReducesDistance(int stepX, int stepZ, int dx, int dz) {
		int now = Math.abs(dx) + Math.abs(dz);
		if (now == 0) return false;
		int next = Math.abs(dx - stepX) + Math.abs(dz - stepZ);
		return next < now;
	}

	/**
	 * 轴向接近矿：哪边差得多走哪边。两边一样时保持当前朝向，避免格边来回拧。
	 * 来源：2026-08-18 顺路铜矿 dx=3、dz=2/3，北/西每拍切换，1×2 里左右横摆。
	 */
	public static Direction stableAxisHeading(int dx, int dz, Direction current) {
		if (dx == 0 && dz == 0) return null;
		Direction byX = dx > 0 ? Direction.EAST : dx < 0 ? Direction.WEST : null;
		Direction byZ = dz > 0 ? Direction.SOUTH : dz < 0 ? Direction.NORTH : null;
		if (Math.abs(dx) > Math.abs(dz)) return byX;
		if (Math.abs(dz) > Math.abs(dx)) return byZ;
		if (current != null && headingReducesDistance(current.getStepX(), current.getStepZ(), dx, dz)) {
			return current;
		}
		return byX != null ? byX : byZ;
	}

	/** 矿就在附近且需要上/下：站住挖阶梯，不要沿通道退出。 */
	public static boolean stayAndClimb(int horizontalManhattan, boolean needsVertical) {
		return needsVertical && horizontalManhattan <= 2;
	}
}
