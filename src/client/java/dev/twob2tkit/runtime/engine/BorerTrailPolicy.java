package dev.twob2tkit.runtime.engine;

/**
 * 回家路点怎么记、怎么画。只改这一处。
 * <p>
 * 金色箭头必须沿着已挖的 1×2，不要拿下界门坐标在主世界画一条穿墙斜线。
 * 画的时候沿记下的路点连续往家走，不要因为绕路或一格台阶把线掐断。
 * 来源：2026-08-21 人在 382879 -55 311290，箭头「西北 483370 格」指向墙壁。
 */
public final class BorerTrailPolicy {
	/** 相邻路点大约 2.2 格，允许中间漏记、小跳和台阶。 */
	public static final int CORRIDOR_MANHATTAN = 12;
	/** 还在这条巷道附近：重新开盾构不要把走过的路清掉。 */
	public static final double RESUME_NEAR_BLOCKS = 32.0;
	/** 离粘住的路点这么远就重新贴最近的，不要继续画远处那截。 */
	public static final double RESTICK_BLOCKS = 12.0;
	/** 眼前这一段巷道。太远的下层旧路不要穿到当前 1×2 里。 */
	public static final int DRAW_NEAR_XZ = 48;
	public static final int DRAW_NEAR_Y = 8;

	private BorerTrailPolicy() {
	}

	/** 两路点是巷道上的一步，不是穿墙斜线。 */
	public static boolean isCorridorSegment(int manhattan) {
		return manhattan > 0 && manhattan <= CORRIDOR_MANHATTAN;
	}

	/** 地狱门只在下界当家。主世界用挖矿起点。 */
	public static boolean includePortalAsHome(boolean inNether) {
		return inNether;
	}

	/** 人还在旧巷道里：接着记，不要 begin 成「门 + 脚底」两条。 */
	public static boolean resumeExistingTrail(double distToNearest) {
		return distToNearest >= 0.0 && distToNearest <= RESUME_NEAR_BLOCKS;
	}

	/** 人已经离开粘住的路点：改贴最近的，箭头从脚边开始。 */
	public static boolean shouldRestick(double distToSticky) {
		return distToSticky > RESTICK_BLOCKS;
	}

	/**
	 * 这一段要不要画。必须在眼前巷道附近。
	 * 来源：2026-08-21 人在 382822 -31，下层 Y=-50 的路点穿墙画在当前 1×2 里。
	 */
	public static boolean drawSegmentNearPlayer(int xzManhattan, int dyAbs) {
		return xzManhattan <= DRAW_NEAR_XZ && dyAbs <= DRAW_NEAR_Y;
	}

	/** 水平已经走出眼前范围：后面通常更远，停笔。只是一格台阶不要停整条。 */
	public static boolean stopDrawingBeyond(int xzManhattan) {
		return xzManhattan > DRAW_NEAR_XZ;
	}

	/**
	 * 画回家线：沿记下的路点一格格往家走，绕路也要连上。
	 * {@code towardHome} 只给走路用，拿来筛线段会把线掐成一段段。
	 */
	public static boolean skipDetourWhenDrawing() {
		return false;
	}

	/** 箭头必须往家走。往后记的路点不能把人指回刚离开的方向。 */
	public static boolean towardHome(double neighborDistSqr, double currentDistSqr) {
		return neighborDistSqr + 0.5 < currentDistSqr;
	}
}
