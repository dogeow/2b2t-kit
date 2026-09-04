package dev.twob2tkit.chopper;

/**
 * 挖树走近：补种/走向树干时树叶挡路。
 * <p>
 * 准星已经打在树叶上却只按 W，会在叶墙里空走直到 approach-stuck。
 * 够得着的树叶立刻剪；剪了一会儿还过不去再飞越。
 */
public final class ChopperApproachPolicy {
	/** 卡住多久才允许飞越叶墙（tick）。 */
	public static final int FLY_OVER_TICKS = 20;
	/** 飞越时相对目标脚底抬高的高度（格）。 */
	public static final double FLY_OVER_HEIGHT = 5.0;

	private ChopperApproachPolicy() {
	}

	/** 准星打在树叶上且够得着、能挖时，先剪挡路叶。 */
	public static boolean shouldMineBlocker(boolean leaves, boolean canBreak, boolean inReach) {
		return leaves && canBreak && inReach;
	}

	/** 卡住 tick 达到阈值则飞越，不要一直按 W。 */
	public static boolean shouldFlyOver(int stuckTicks) {
		return stuckTicks >= FLY_OVER_TICKS;
	}

	/** 飞越悬停高度：目标脚底 Y + {@link #FLY_OVER_HEIGHT}。 */
	public static double flyOverFeetY(double destY) {
		return destY + FLY_OVER_HEIGHT;
	}

	/** 水平还远且人低于悬停高度时继续爬升。 */
	public static boolean shouldAscendOver(double playerY, double hoverY, double horiz) {
		return horiz > 0.8 && playerY < hoverY - 0.35;
	}

	/** 已贴近目标且人偏高时下落，落到补种/砍树高度。 */
	public static boolean shouldDescendToDest(double playerY, double destY, double horiz) {
		return horiz < 1.2 && playerY > destY + 1.2;
	}

	/** 够得着就落地砍。空中挖更慢，开关飞行还会把人晃起来。 */
	public static boolean flyWhenInReach() {
		return false;
	}

	/** 够得着却没挖成：站住砍准星那块，不要按 W / 起飞。 */
	public static boolean walkAfterMineFail(boolean inReach) {
		return !inReach;
	}

	/** 挡路树叶/原木被 stall skip 后仍在眼前：再砍一次，不要改去飞近。 */
	public static boolean retryIgnoredLeaf(boolean leaves) {
		return leaves;
	}

	/** 树叶或原木被跳过后，若仍挡路可再试一次。 */
	public static boolean retryIgnoredTreeBlock(boolean leaves, boolean wood) {
		return leaves || wood;
	}

	/** 够得着却一直对不齐：约两秒后跳过这块，不要永远站住。 */
	public static final int STAND_FAIL_TICKS = 40;

	/** 站住砍却对不齐超时则放弃这块。 */
	public static boolean giveUpStandStill(int ticks) {
		return ticks >= STAND_FAIL_TICKS;
	}

	/** 够得着时瞬间对准，不要平滑转头导致每拍 clip-miss。 */
	public static boolean snapLookWhenInReach(boolean inReach) {
		return inReach;
	}
}
