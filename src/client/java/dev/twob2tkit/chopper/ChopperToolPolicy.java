package dev.twob2tkit.chopper;

/**
 * 挖树选工具。
 * <p>
 * 保留至少 10% 耐久，避免磨损工具继续工作；没有可用工具时改用不会磨损的物品。
 */
public final class ChopperToolPolicy {
	/** 与 Meteor auto-tool anti-break-percentage 默认值一致。 */
	public static final int ANTI_BREAK_PERCENT = 10;
	/** 剩余耐久绝对下限；再低也不握在手上。 */
	public static final int MIN_REMAINING = 8;

	private ChopperToolPolicy() {
	}

	/**
	 * 工具是否已「太旧」：剩余耐久过低或低于最大耐久的 anti-break 比例。
	 *
	 * @param remaining 剩余耐久
	 * @param maxDamage 最大耐久（0 表示不可损）
	 */
	public static boolean tooWorn(int remaining, int maxDamage) {
		if (maxDamage <= 0) return false;
		if (remaining <= MIN_REMAINING) return true;
		return remaining < maxDamage * ANTI_BREAK_PERCENT / 100;
	}

	/** 保留可用的当前槽，否则先快捷栏后背包；没有安全选择返回 -1。 */
	public static int chooseSlot(int selected, int slots, java.util.function.IntPredicate usable) {
		if (selected >= 0 && selected < slots && usable.test(selected)) return selected;
		for (int slot = 0; slot < slots; slot++) if (usable.test(slot)) return slot;
		return -1;
	}
}
