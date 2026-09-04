package dev.twob2tkit.chopper;

/**
 * 挖树选工具。
 * <p>
 * Meteor {@code auto-tool} 的 anti-break（默认 10% 耐久）会取消破坏并松开左键，
 * 快坏的剪刀拿在手上就一直挖不动。低于阈值时不要选它，叶子改空手。
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

	/** 没有可用剪刀时，叶子改空手挖，避免快坏剪刀被 Meteor 取消。 */
	public static boolean useFistForLeaves(boolean hasUsableShears) {
		return !hasUsableShears;
	}

	/** 当前手持已是目标类型且未磨损则保持，不要每拍换槽。 */
	public static boolean keepCurrentTool(boolean isDesiredType, boolean worn) {
		return isDesiredType && !worn;
	}
}
