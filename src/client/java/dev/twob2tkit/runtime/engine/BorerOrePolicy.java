package dev.twob2tkit.runtime.engine;

/**
 * 找矿时「矿已经在身旁」的判定。只改这一处。
 * <p>
 * 贴着矿、1×2 已通时要挖矿，不要报「没有可挖视线」对着远处石头空等。
 * 头顶天花板（相对脚 dy=2）够得着也挖，不要先去开旁边的通道。
 */
public final class BorerOrePolicy {
	private BorerOrePolicy() {
	}

	/**
	 * 矿在身旁一格（含脚下那层、头顶天花板）：够得着就挖，不要等视线、不要先去挖通道石头。
	 * 1×2 头顶那格相对脚是 dy=2。
	 * @param horizontalManhattan 脚到矿的水平曼哈顿距离
	 * @param dy 矿相对脚的高度，负值是脚下
	 */
	public static boolean mineAdjacentInsteadOfWait(int horizontalManhattan, int dy) {
		return horizontalManhattan <= 1 && dy >= -1;
	}

	/** 贴着矿且前方 1×2 已是空气时，不要标成被遮挡。 */
	public static boolean waitWouldSkipAdjacentOre(int horizontalManhattan, int dy, boolean frontOpen) {
		return frontOpen && mineAdjacentInsteadOfWait(horizontalManhattan, dy);
	}

	/**
	 * 勾选矿在身旁或脚下那层：挖矿，不要站住「不退出通道」。
	 * 前方墙还在也挖底下的矿；通道通不通不再当门槛。
	 * 来源：2026-08-19 铁矿 382837 -3，人在 382836 -2，前方墙还在。
	 */
	public static boolean mineAdjacentInsteadOfHold(int horizontalManhattan, int dy, boolean frontOpen) {
		return mineAdjacentInsteadOfWait(horizontalManhattan, dy);
	}

	/**
	 * 身旁/脚下勾选矿要不要挖。
	 * 脚下那层挖掉会掉下去：落地安全（无岩浆/虚空/超深）才挖。立足点就是矿也挖。
	 */
	public static boolean mineAdjacentOre(int horizontalManhattan, int dy, boolean standingSupport, boolean landingSafe) {
		if (!mineAdjacentInsteadOfWait(horizontalManhattan, dy)) return false;
		if (dy == -1 || standingSupport) return landingSafe;
		return true;
	}

	/**
	 * 找哪块矿：越小越先挖。身旁/脚下永远排在远处同层前面。
	 * 旧公式 {@code dx²+dz²+dy²*25} 会让 4 格外平地矿（16）压过脚下矿（25）。
	 */
	public static double approachScore(int dx, int dz, int dy) {
		int horiz = Math.abs(dx) + Math.abs(dz);
		int ady = Math.abs(dy);
		if (mineAdjacentInsteadOfWait(horiz, dy)) {
			return horiz + ady * 0.25;
		}
		return 8.0 + horiz + ady * 0.5;
	}

	/** 新矿比已锁目标更近，该换。身旁/脚下对远处永远换。 */
	public static boolean preferNewOre(double newScore, double lockedScore) {
		return newScore + 0.01 < lockedScore;
	}
}
