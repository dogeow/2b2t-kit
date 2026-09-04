package dev.twob2tkit.cruise;

/**
 * 巡航升空挖哪一格。只改这一处。
 * <p>
 * 准星锁在前上方时会打到巷道侧壁。只挖玩家碰撞箱正上方会挡住往上移的方块。
 * 来源：2026-08-24 人在 17922 -3 7898，挖的是 17921,-1 和 17920,0，不是头顶。
 */
public final class CruiseCeilingPolicy {
	private CruiseCeilingPolicy() {
	}

	/** 这一格的 XZ 是否在人正上方（碰撞箱覆盖的列）。 */
	public static boolean inAscentColumn(int x, int z, int minX, int maxX, int minZ, int maxZ) {
		return x >= minX && x <= maxX && z >= minZ && z <= maxZ;
	}

	/** 前上方视线打到侧壁时不要当头顶。 */
	public static boolean acceptLookHit(boolean inAscentColumn) {
		return inAscentColumn;
	}

	/** 先挖更低、更挡住上升的。 */
	public static int ascentOrder(int blockY, int minY, double distSqr) {
		int dy = Math.max(0, blockY - minY);
		int dist = (int) Math.min(999_999, Math.round(distSqr * 100.0));
		return dy * 1_000_000 + dist;
	}
}
