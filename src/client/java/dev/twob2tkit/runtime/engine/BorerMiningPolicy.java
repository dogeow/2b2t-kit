package dev.twob2tkit.runtime.engine;

import java.util.Objects;

/**
 * 挖掘授权、失败重试与身旁矿选择的纯规则。
 * <p>
 * 这里的 {@code actualHit} 只表示客户端真实射线命中的方块；用于转向的合成命中
 * 不能传入，真实准星没有命中时应传 {@code null}。
 */
final class BorerMiningPolicy {
	private BorerMiningPolicy() {
	}

	/** 只有真实准星命中预期方块且仍在触及时，才允许按住攻击。 */
	static boolean allowAttack(Object expectedTarget, Object actualHit, boolean inReach) {
		return inReach
			&& expectedTarget != null
			&& actualHit != null
			&& Objects.equals(expectedTarget, actualHit);
	}

	/** 普通通道遮挡连续没有进度时短期排除；矿石主目标交给矿石失败流程处理。 */
	static boolean shouldSuppressRetry(boolean isOreTarget, boolean noProgress) {
		return noProgress && !isOreTarget;
	}

	/** 准星未命中时只看前方是否安全；已经进入理论触及距离不能成为原地空等的理由。 */
	static boolean shouldWalkAfterAimMiss(boolean safeToWalk) {
		return safeToWalk;
	}

	/**
	 * 勾选矿已在可挖距离：真实准星打到另一块可挖方块时改挖这块。
	 * 轴向瞄准对角矿会打到旁边石头；不要当侧壁丢掉后只报打不到。
	 */
	static boolean mineRealHitTowardInReachOre(boolean oreInReach, boolean hitIsExpected, boolean hitIsMineable) {
		return oreInReach && !hitIsExpected && hitIsMineable;
	}

	/**
	 * 轴向瞄准没命中、转到矿的可见面就能打到：对着可见面挖，不要继续轴向空挥。
	 */
	static boolean useVisibleFaceWhenAxisMisses(boolean inReach, boolean axisHits, boolean visibleFaceHits) {
		return inReach && !axisHits && visibleFaceHits;
	}

	/**
	 * 脚前是矿/石头、头前也是能挖的方块：先挖头开 1×2。
	 * 站在同高时眼睛在头那一层，lookAxis 打到头，死盯脚前矿会准星不命中。
	 * 来源：2026-08-21 钻石 382859 -51 311313，实际命中 382859 -50 311313。
	 */
	static boolean mineHeadToSeeAdjacentOre(boolean frontMineable, boolean headMineable) {
		return frontMineable && headMineable;
	}

	/** 侧向方块若真的挡住人物下一步碰撞箱，它就是路线挡路，不能当无关侧墙丢掉。 */
	static boolean rejectAsSideWall(boolean offCorridor, boolean blocksProjectedMovement) {
		return offCorridor && !blocksProjectedMovement;
	}

	/** 被短期排除的候选不能立刻再次成为当前目标。 */
	static boolean canSelectTarget(boolean mineable, boolean suppressed) {
		return mineable && !suppressed;
	}

	/** 该挖矿目标是否仍在抑制期内。 */
	static boolean suppressionActive(long now, long until) {
		return until > now;
	}

	/**
	 * 沿用身旁矿规则。立足点就是矿时，落地安全（无岩浆/虚空/超深）也可以挖。
	 */
	static boolean adjacentOreCanBeSelected(int horizontalManhattan, int dy, boolean standingSupport, boolean landingSafe) {
		return BorerOrePolicy.mineAdjacentOre(horizontalManhattan, dy, standingSupport, landingSafe);
	}
}
