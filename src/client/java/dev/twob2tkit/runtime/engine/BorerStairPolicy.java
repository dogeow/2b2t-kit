package dev.twob2tkit.runtime.engine;

/**
 * 找矿时向下接近：什么时候挖台阶、什么时候走下去。只改这一处。
 * <p>
 * 前方 1×2 已通、脚下仍是平地时要挖前方地板做出一格台阶。
 * 不要设成「向下挖阶梯」然后按着前进空走。
 * <p>
 * 下去之后看 F3 朝向那一列：脚前空、头前有方块，挖头就有 1×2。不要报过不去。
 */
public final class BorerStairPolicy {
	private BorerStairPolicy() {
	}

	/** 前方落差是 0：平地，挖前方地板。 */
	public static boolean shouldCutFloor(int drop) {
		return drop == 0;
	}

	/** 前方已经是安全坑：走下去，不要再挖地板。 */
	public static boolean shouldWalkDown(int drop) {
		return BorerFallPolicy.shouldWalkIntoDrop(drop);
	}

	/**
	 * 矿比当前脚低 1 是地板那层，平着走过去挖。低 2 格才下台阶。
	 * 高于 1×2 头顶（dy 大于 2）才向上。
	 * 来源：2026-08-19 人在 y=-5，铁矿 y=-6，提示「向下挖阶梯」空站。
	 */
	public static boolean needsVerticalRoute(int dy) {
		return dy > 2 || dy < -1;
	}

	/**
	 * 已经进了向下模式：前方平地或安全落差都走，不要空站。
	 * 1 格落差直接跨下去。
	 */
	public static boolean shouldWalkWhileDescending(int drop) {
		return BorerFallPolicy.canWalk(drop);
	}

	/**
	 * Meteor Step（或步高≥1）且前方是 1 格台阶、头顶已通：走上去。
	 * 只有矿比人高才走；矿更低或同层时这块是墙，要挖开 1×2。
	 * 来源：2026-08-25 13619 -59 9181，眼前深板岩，矿在 -60，报没视线空等 4 秒。
	 */
	public static boolean walkUpOneBlockStep(
		boolean canStepOneBlock, boolean stepInFront, boolean headroomClear, boolean climbing
	) {
		return canStepOneBlock && stepInFront && headroomClear && climbing;
	}

	/**
	 * 最前层够得着的全是可跨台阶：走上去，不要标「没视线」原地等。
	 * 还有别的挡路才算遮挡。
	 */
	public static boolean occludeWhenFrontBlocked(boolean anyReachable, boolean onlyWalkableSteps) {
		return anyReachable && !onlyWalkableSteps;
	}

	/** 该挖的台阶地板：身旁一格、比脚低 1。立足点不算。 */
	public static boolean isCutFloor(int horizontalManhattan, int dy) {
		return horizontalManhattan == 1 && dy == -1;
	}

	/**
	 * 脚前已空、头前能挖：挖头开 1×2。
	 * 两边都是实心是侧壁，不要用这条去挖。
	 */
	public static boolean mineHeadToOpenOneByTwo(boolean feetPassable, boolean headMineable) {
		return feetPassable && headMineable;
	}

	/** 隔壁柱子高于 1×2 的沙砾先不管，眼前通道还没通。 */
	public static boolean ignoreOverheadFalling(int dist, int dy, int corridorHeight) {
		return dist > 0 && dy > corridorHeight;
	}

	/**
	 * 已经在可挖距离内、准星也能打到：对准挖，不要「走近再挖」把视角拧向矿。
	 * 够得着但射线打到坑底/别的块：不要空挥，改挖眼前 1×2。
	 */
	public static boolean keepAimingInsteadOfWalking(boolean inReach, boolean aimHits) {
		return inReach && aimHits;
	}

	/** 矿还不在当前列：开 1×2 朝矿，不要先挖 F3 反方向。已经在目标列才用朝向。 */
	public static boolean tryOreHeadingFirst(int horizontalManhattan) {
		return horizontalManhattan > 0;
	}
}
