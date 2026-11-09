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

	/** 站在岩浆块上挖逃生口：不能每帧松手，否则挖掘进度清零，永远挖不开。 */
	public static boolean keepMagmaExitDig(boolean onMagma, boolean lavaContact, boolean inWater, boolean targetIsMagma) {
		return onMagma && !lavaContact && !inWater && targetIsMagma;
	}

	/** 脚下或前方落脚是岩浆块、脚下和四周都没有岩浆时，蹲着不掉血，照常挖、照常走，不逃离也不起飞。 */
	public static boolean sneakOnMagma(boolean magmaWalk, boolean magmaFloor, boolean lavaContact, boolean inWater, boolean lavaBesideOrBelow) {
		return magmaWalk && magmaFloor && !lavaContact && !inWater && !lavaBesideOrBelow;
	}

	/** 专挖岩浆块且目标不在脚下更低处：平走不挖地面，地面下的岩浆不算挡路；要往下挖时仍按原规则。 */
	public static boolean ignoreLiquidUnderFloor(boolean magmaMining, int goalDy) {
		return magmaMining && goalDy >= 0;
	}

	/** 下面和四周都没有岩浆的岩浆块可以蹲着站上去：顺路经过、走过去捡掉落物都行。 */
	public static boolean safeMagmaFloor(boolean magmaWalk, boolean magma, boolean lavaBesideOrBelow) {
		return magmaWalk && magma && !lavaBesideOrBelow;
	}

	/** 不掉血的落差（0–3 格）落到安全岩浆块：直接蹲着走下去，不要在岩浆块上垫方块。 */
	public static boolean dropOntoSafeMagma(int depth, boolean safeMagma) {
		return safeMagma && depth >= 0 && depth <= 3;
	}

	/** 小漏水是否该走近再封。 */
	public static boolean shouldWalkToLeak(boolean leak, boolean inReach, double distSqr, boolean sealFailed) {
		return leak && (!inReach || sealFailed && distSqr > APPROACH_DIST_SQR);
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

	/**
	 * 真踩进岩浆流体：优先停挖并在地面退开，不要为了逃生新开 Meteor 飞行。
	 * 靠近岩浆湖本身不是接触，接触判定仍由 {@code player.isInLava()} 负责。
	 */
	public static boolean preferGroundRetreatFromLava(boolean touchedLavaFluid, boolean groundStepAvailable) {
		return touchedLavaFluid && groundStepAvailable;
	}

	/** 岩浆接触时不要新启飞行；已在飞只保留既有状态，避免 thrash 进更多岩浆。 */
	public static boolean allowEnableFlightForLava(boolean alreadyFlying) {
		return false;
	}

	/** 地面退不开时：停机/停步，而不是强行起飞。 */
	public static boolean stopInsteadOfFlightThrash(boolean touchedLavaFluid, boolean groundStepAvailable) {
		return touchedLavaFluid && !groundStepAvailable;
	}
}
