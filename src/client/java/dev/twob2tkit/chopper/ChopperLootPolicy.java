package dev.twob2tkit.chopper;

/**
 * 挖树捡掉落物：树苗经常卡在树冠树叶上，关掉飞行按跳只会原地弹。
 * 高了就飞，地面只跳一格台阶。
 */
public final class ChopperLootPolicy {
	private ChopperLootPolicy() {
	}

	/** 掉落物比人高一格多，或低两格以上，走路到不了。 */
	public static boolean shouldFly(double dy) {
		return dy > 1.25 || dy < -2.0;
	}

	/** 原版拾取看水平距离；3D 距离在 1.0 附近抖动时不要一直按 W。 */
	public static boolean closeEnoughForPickup(double horiz, double dy, double dist) {
		if (dist <= 1.25) return true;
		return horiz <= 1.0 && Math.abs(dy) <= 1.25;
	}

	/** 够近了就站住等拾取，不要来回蹭。 */
	public static boolean shouldWalkForward(double horiz, double dy, double dist, boolean flying) {
		if (closeEnoughForPickup(horiz, dy, dist)) return false;
		return horiz > 0.35 || flying && Math.abs(dy) > 0.45;
	}

	/** 没开飞行时，空中按跳就是原地弹。 */
	public static boolean shouldJump(boolean flying, boolean onGround, double dy) {
		if (flying) return dy > 0.45;
		return onGround && dy > 0.45 && dy <= 1.25;
	}

	/** 弹跳会让距离抖 0.2，不能当靠近；已贴近时阈值更严，避免 1.0↔1.3 永远重置 stuck。 */
	public static boolean progressResetsStuck(double distance, double bestDist) {
		if (distance >= bestDist) return false;
		double margin = distance < 1.5 ? 0.35 : 0.45;
		return distance + margin < bestDist;
	}

	/** 树冠上要飞；掉在脚边或更低时要落地捡，不要挂着飞行往前蹭。 */
	public static boolean keepFlightForLockedTarget(boolean flightLatched, double dy, boolean targetActive) {
		if (!targetActive) return false;
		if (dy < -0.35) return false;
		return flightLatched || shouldFly(dy);
	}

	/** 锁定的实体仍有效时不因旁边出现更近掉落物而换目标。 */
	public static boolean keepLockedTarget(boolean currentAlive, boolean currentIgnored) {
		return currentAlive && !currentIgnored;
	}

	/** 树冠里连续一秒没靠近且真实路径命中可挖树叶：先清叶，再继续同一掉落物。 */
	public static boolean shouldClearLeafObstacle(
		int stuckTicks,
		boolean hitLeaves,
		boolean hitInReach
	) {
		return stuckTicks >= 20 && hitLeaves && hitInReach;
	}
}
