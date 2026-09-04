package dev.twob2tkit.runtime.engine;

import net.minecraft.core.Direction;

/**
 * 向下挖竖井截面怎么对齐脚下。只改这一处。
 * <p>
 * 边长奇数时左右前后对称；偶数时多出来的格子在朝向的右侧和前方。
 * 4×4：左/后各 1，右/前各 2，原点是脚下那一格。
 */
public final class BorerShaftPolicy {
	private BorerShaftPolicy() {
	}

	/** 巷道起点横向偏移。 */
	public static int startOffset(int size) {
		int n = Math.max(1, size);
		return -((n - 1) / 2);
	}

	/** 巷道终点横向偏移。 */
	public static int endOffset(int size) {
		int n = Math.max(1, size);
		return startOffset(n) + n - 1;
	}

	/** 例如朝北、宽 4：西1东2。 */
	public static String spanLabel(int start, int end, String towardNegative, String towardPositive) {
		int neg = Math.max(0, -start);
		int pos = Math.max(0, end);
		return towardNegative + neg + towardPositive + pos;
	}

	/** 巷道原点相对提示文案。 */
	public static String originHint(int wide, int along, String left, String right, String back, String forward) {
		return wide + "×" + along + " 从脚下这格  "
			+ spanLabel(startOffset(wide), endOffset(wide), left, right) + "  "
			+ spanLabel(startOffset(along), endOffset(along), back, forward);
	}

	/**
	 * 预览确认期间用哪条朝向画截面。
	 * {@code locked} 是第一次按 B 记下的朝向；必须用它，不能换成当前视角，
	 * 否则转头范围跟着转，没法确认。
	 */
	public static Direction headingForPreview(Direction locked, Direction currentLook) {
		if (locked != null && locked.getAxis() != Direction.Axis.Y) return locked;
		if (currentLook != null && currentLook.getAxis() != Direction.Axis.Y) return currentLook;
		return Direction.SOUTH;
	}

	/**
	 * 预览切面最低格（相对脚下，含）。下一层也会挖，要画出来。
	 */
	public static int previewSliceMinDy() {
		return -1;
	}

	/**
	 * 预览切面最高格（相对脚下，含）。含头顶那格，旁边高地才能在墙面上看到范围。
	 * 再往上的山体不会挖，不要画到山顶。
	 */
	public static int previewSliceMaxDy() {
		return 1;
	}

	/** AABB 上沿（不含），给 {@code new AABB(..., yMax, ...)}。 */
	public static int previewSliceMaxYExclusive(int feetY) {
		return feetY + previewSliceMaxDy() + 1;
	}

	/** 预览切片最低 Y。 */
	public static int previewSliceMinY(int feetY) {
		return feetY + previewSliceMinDy();
	}
}
