package dev.twob2tkit.chopper;

/**
 * 挖树挥镐节奏。秒破（剪刀砍树叶）每拍点一下，但这一拍仍要按住。
 */
public final class ChopperMinePolicy {
	private ChopperMinePolicy() {
	}

	/**
	 * 剪刀砍树叶是秒破：每拍点一下。
	 */
	public static boolean oneClickBreaks(float destroyProgress) {
		return destroyProgress >= 1.0f;
	}

	/** 本拍是否要点攻击：新目标、重试、秒破或完全没进度。 */
	public static boolean clickThisTick(boolean newTarget, boolean retryDue, boolean insta, boolean noProgress) {
		return newTarget || retryDue || insta || noProgress;
	}

	/**
	 * 正在挖就按住。秒破点完立刻 {@code setDown(false)} 会让原版
	 * {@code continueAttack(false)} 马上 {@code stopDestroyBlock}，
	 * Folia 上叶子一直 stage=-1（2026-09-01 382800,74,311320 attack=false 200 拍）。
	 */
	public static boolean holdAttack(boolean insta, boolean clickedThisTick) {
		return !insta || clickedThisTick;
	}
}
