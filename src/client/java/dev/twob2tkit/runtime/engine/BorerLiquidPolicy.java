package dev.twob2tkit.runtime.engine;

/**
 * 区域挖遇水：一格漏水跑过去换成石头；大水面不要填湖，换一口井。
 */
public final class BorerLiquidPolicy {
	public static final int LAKE_WATER_NEIGHBORS = 3;
	public static final int LEAK_MAX_WATER_NEIGHBORS = 2;
	public static final int FAIL_GIVE_UP = 3;
	public static final double APPROACH_DIST_SQR = 2.25;

	private BorerLiquidPolicy() {
	}

	/** 邻接水面是否多到算湖。 */
	public static boolean isLake(int waterNeighbors) {
		return waterNeighbors >= LAKE_WATER_NEIGHBORS;
	}

	/** 旁边有固体、水体不超过两面：从附近流下来的一格漏水。 */
	public static boolean isSmallLeak(int waterNeighbors, int solidNeighbors) {
		return waterNeighbors <= LEAK_MAX_WATER_NEIGHBORS && solidNeighbors >= 1;
	}

	/** 湖中间的水不要拿来封；贴身湖水也别填，换井。 */
	public static boolean ignoreLakeCandidate(boolean area, int waterNeighbors) {
		return area && isLake(waterNeighbors);
	}

	/** 遇湖是否跳过本井。 */
	public static boolean skipShaftForLake(boolean area, int waterNeighbors) {
		return area && isLake(waterNeighbors);
	}

	/** 小漏水是否该走近再封。 */
	public static boolean shouldWalkToLeak(boolean leak, boolean inReach, double distSqr) {
		return leak && (!inReach || distSqr > APPROACH_DIST_SQR);
	}

	/** 连续封失败是否放弃。 */
	public static boolean giveUpAfterFails(int consecutiveFails) {
		return consecutiveFails >= FAIL_GIVE_UP;
	}

	/** 放置后等待落稳拍数。 */
	public static int settleTicks(boolean placed, boolean area) {
		if (placed) return 6;
		return area ? 0 : 4;
	}
}
