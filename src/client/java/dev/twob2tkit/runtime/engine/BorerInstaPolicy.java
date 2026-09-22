package dev.twob2tkit.runtime.engine;

/**
 * 下界镐等能一拳打碎石头时：点一下就换下一块，不要按住同一格。
 * 原版 {@code getDestroyProgress >= 1} 就是 startDestroyBlock 当场挖掉。
 */
final class BorerInstaPolicy {
	private BorerInstaPolicy() {
	}

	/** 原版一拳可碎（destroyProgress≥1）。 */
	static boolean oneClickBreaks(float destroyProgress) {
		return destroyProgress >= 1.0f;
	}

	/** 一拳能碎：只点一下。碎不掉才按住。 */
	static boolean holdAttack(boolean oneClickBreaks) {
		return !oneClickBreaks;
	}

	/** 即使本地秒破也留出确认窗口；真正的服务器预测确认另由引擎检查。 */
	static int clearConfirmTicks(boolean lastClickBrokeInstantly, int defaultTicks) {
		return Math.max(0, defaultTicks);
	}

	/** 新目标、到了重试拍、或这格能秒破：这一拍要点一下。 */
	static boolean clickThisTick(boolean newTarget, boolean retryDue, boolean oneClickBreaks) {
		return newTarget || retryDue || oneClickBreaks;
	}
}
