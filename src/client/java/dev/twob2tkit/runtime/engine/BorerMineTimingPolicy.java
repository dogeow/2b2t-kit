package dev.twob2tkit.runtime.engine;

/**
 * 按镐、附魔、急迫、水下、方块记住挖法。
 * 人手点一下就能碎的石头：按住的拍数用破坏进度算出，裂纹满了立刻换下一块，
 * 不要等客户端空气、更不要按住十几拍。
 */
final class BorerMineTimingPolicy {
	static final int MAX_SAMPLE_TICKS = 200;
	static final int INSTA_FAIL_TICKS = 2;

	private BorerMineTimingPolicy() {
	}

	/** 一次挖矿节奏记忆。 */
	public record Memory(boolean insta, int holdTicks) {
	}

	/** 节奏记忆缓存键。 */
	static String key(String tool, String enchants, int haste, int conduit, boolean wet, String block) {
		String t = blank(tool, "hand");
		String e = enchants == null ? "" : enchants;
		String b = blank(block, "unknown");
		return t + "|" + e + "|h" + Math.max(0, haste) + "|c" + Math.max(0, conduit)
			+ (wet ? "|wet" : "") + "|" + b;
	}

	/** 一拳进度。>=1 秒破；>=0.5 人手点一下的时长就够。 */
	static int ticksToBreak(float destroyProgress) {
		if (destroyProgress >= 1.0f) return 1;
		if (destroyProgress <= 0.0f) return MAX_SAMPLE_TICKS;
		return Math.max(1, (int)Math.ceil(1.0 / destroyProgress));
	}

	/** 裂纹阶段是否完成。 */
	static boolean crackComplete(int destroyStage) {
		return destroyStage >= 9;
	}

	/** 破坏进度是否像点一下就够。 */
	static boolean tapSized(float destroyProgress) {
		return ticksToBreak(destroyProgress) <= 2;
	}

	/** 结合已挖拍数得到有效记忆。 */
	static Memory effective(Memory remembered, int ticksOnThisBlock) {
		if (remembered != null && remembered.insta && ticksOnThisBlock >= INSTA_FAIL_TICKS) return null;
		return remembered;
	}

	/** 本拍是否要点攻击。 */
	static boolean shouldClick(Memory remembered, float destroyProgress, boolean newTarget, boolean retryDue, int ticksOnThisBlock) {
		if (ticksToBreak(destroyProgress) == 1) return ticksOnThisBlock == 0 || retryDue;
		Memory m = effective(remembered, ticksOnThisBlock);
		if (m != null && m.insta) return ticksOnThisBlock == 0 || retryDue;
		if (ticksOnThisBlock == 0) return true;
		return newTarget || retryDue;
	}

	/** 本拍是否应按住攻击。 */
	static boolean shouldHold(Memory remembered, float destroyProgress, int ticksOnThisBlock, boolean crackComplete) {
		int need = ticksToBreak(destroyProgress);
		if (need <= 1) return false;
		Memory m = effective(remembered, ticksOnThisBlock);
		if (m != null && m.insta) return false;
		if (tapSized(destroyProgress)) {
			if (crackComplete) return false;
			if (m != null && m.holdTicks > 0) need = Math.min(need, m.holdTicks);
			return ticksOnThisBlock < need;
		}
		// 下界金矿、残骸：裂纹满了也按住。松手会 cancel 破坏，然后「确认服务器」空转重试。
		return true;
	}

	/** 本格是否挖完可换下一块。 */
	static boolean doneWithBlock(int ticksOnThisBlock, float destroyProgress, boolean crackComplete) {
		if (!tapSized(destroyProgress)) return false;
		if (crackComplete && ticksOnThisBlock >= 1) return true;
		int need = ticksToBreak(destroyProgress);
		return ticksOnThisBlock > need;
	}

	/** 根据本格观测生成记忆。 */
	static Memory remember(boolean held, int ticks, float destroyProgress) {
		int need = ticksToBreak(destroyProgress);
		if (need <= 1) return new Memory(true, 0);
		if (ticks < 1 || ticks >= MAX_SAMPLE_TICKS) return null;
		if (!held && ticks <= INSTA_FAIL_TICKS) return new Memory(true, 0);
		return new Memory(false, Math.min(Math.max(1, ticks), need));
	}

	/** 合并新旧节奏记忆。 */
	static Memory combine(Memory previous, Memory observed) {
		if (observed == null) return previous;
		if (previous == null) return observed;
		if (observed.insta || previous.insta) return new Memory(true, 0);
		return new Memory(false, Math.min(previous.holdTicks, observed.holdTicks));
	}

	/** 空串则用回退值。 */
	private static String blank(String value, String fallback) {
		return value == null || value.isBlank() ? fallback : value;
	}
}
