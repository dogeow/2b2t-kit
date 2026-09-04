package dev.twob2tkit.runtime.engine;

/**
 * 落差能不能走、要不要铺路。只改这一处。
 * <p>
 * 2026-08-15 定过：认 Meteor NoFall；没开最多 3 格，开了更深也可以。
 * 1.6.149 为了修挖穿立足点，曾改成「空气就铺路、只许下 1 格」，把这条盖掉了。
 */
public final class BorerFallPolicy {
	public static final int DEFAULT_MAX_BLOCKS = 3;
	public static final int NOFALL_MAX_BLOCKS = 48;

	private BorerFallPolicy() {
	}

	/** 安全落差格数：开 NoFall 最多 48，否则 3。 */
	public static int maxSafeFallBlocks(boolean noFall) {
		return noFall ? NOFALL_MAX_BLOCKS : DEFAULT_MAX_BLOCKS;
	}

	/**
	 * {@code drop} 来自已经按 {@link #maxSafeFallBlocks(boolean)} 截过的扫描：
	 * 0 平地，正数可落格数，-1 岩浆/虚空/太深。
	 */
	public static boolean canWalk(int drop) {
		return drop >= 0;
	}

	/** 往更高的矿走时，1 格台阶照走（能跳回来）；更深才避开，免得把高度走丢。 */
	public static final int CLIMBING_MAX_STEP_DOWN = 1;

	/** 前方是安全坑：走进去，不要铺路、不要停步。 */
	public static boolean shouldWalkIntoDrop(int drop) {
		return drop > 0;
	}

	/**
	 * 矿在更高处时不要跳进深坑（会在格边左右横摆）。
	 * 1 格落差是台阶：走下去，不要空站「前方落差不跳」。
	 * 来源：2026-08-21 人在 382836 -54，钻石在 -53，前方 1 格空气却 WAIT。
	 */
	public static boolean shouldWalkIntoDrop(int drop, boolean climbingToOre) {
		if (climbingToOre) return drop > 0 && drop <= CLIMBING_MAX_STEP_DOWN;
		return shouldWalkIntoDrop(drop);
	}

	/**
	 * 往上接近矿、前方落差超过可跨的 1 格台阶：不要空站。
	 * 够得着就挖，否则垫台阶 / 脚手架 / 飞上去。
	 * 来源：2026-08-25 13598 -56 9181，钻石 13597 -54 9182 距离 1.3，前方空气空等。
	 */
	public static boolean climbDropNeedsAscent(int drop, boolean climbingToOre) {
		return climbingToOre && drop > CLIMBING_MAX_STEP_DOWN;
	}

	/** 矿已经在可挖距离：先挖通路或矿，不要因为前方落差走开或空站。 */
	public static boolean mineInReachInsteadOfWaitClimbDrop(boolean oreInReach, boolean climbDropNeedsAscent) {
		return oreInReach && climbDropNeedsAscent;
	}

	/** 只有不安全才铺路。2 格、3 格、开了 NoFall 的深坑都不垫。 */
	public static boolean shouldBridge(int drop) {
		return drop < 0;
	}

	/**
	 * 挖掉脚下/前方地板后还能站住或安全落下。
	 * {@code dropAfterMine} 把那格当空气再算：0 平地，正数可落，-1 岩浆/虚空/太深。
	 */
	public static boolean canMineFloorIfLandingSafe(int dropAfterMine) {
		return dropAfterMine >= 0;
	}

	/** 挖不动或够不着时，前方安全落差就走下去，不要对着坑沿侧块「走近再挖」。 */
	public static boolean abandonMineAndWalkDrop(int drop, boolean miningStuck) {
		return miningStuck && shouldWalkIntoDrop(drop);
	}

	/** 安全落差已经连续按前进约 2 秒仍不动，才进入垫块/飞行兜底。 */
	public static boolean shouldRecoverStalledSafeDrop(int drop, int stalledTicks) {
		return shouldWalkIntoDrop(drop) && stalledTicks >= 40;
	}

	/** 兜底垫块不能盖住矿石，也不能填掉当前目标所在的下降列。 */
	public static boolean shouldBridgeStalledSafeDrop(
		int drop,
		int stalledTicks,
		boolean supportContainsOre,
		boolean supportOnGoalColumn
	) {
		return shouldRecoverStalledSafeDrop(drop, stalledTicks)
			&& !supportContainsOre && !supportOnGoalColumn;
	}

	/**
	 * 区域挖松键下落：脚下一格已是空气，且按 3/48 格规则能找到安全落点。
	 * {@code safeDropDepth} 来自 {@link BorerHazards#safeFallDepth}，-1 表示岩浆/水/太深。
	 */
	public static boolean areaCanFall(boolean airBelow, int safeDropDepth) {
		return airBelow && canWalk(safeDropDepth);
	}
}
