package dev.twob2tkit.runtime.engine;

/**
 * 找矿捡掉落物。只改这一处。
 * <p>
 * 背包多了几颗不算捡完：地上还有同类就要继续。时运后几颗客户端可能晚几拍才出现，
 * 生成窗口没过完不要收工。原版拾取箱是 {@code inflate(1, 0.5, 1)}，坑底再低 1 格
 * 站在坑沿捡不到，安全落差要走下去。水平墙挡住时不要当成落差。
 * 来源：2026-08-21 钻石 382842 -47 311314，4→6 就收工，坑里还剩 ×3；
 * 2026-08-25 13624 -53 9217，19→21 remaining=false，14 tick 收工，1.6 格外还掉着；
 * 2026-08-26 背包 6→8 remaining=false 仍「等待更多钻石」空等 40 拍。
 */
public final class BorerLootPolicy {
	/** 刚挖掉、掉落物还没出现。 */
	public static final int FIRST_SPAWN_TICKS = 40;
	/** 已经捡进背包、地上看不见：时运晚到最多再等这几拍。 */
	public static final int EXTRA_SPAWN_TICKS = 8;

	private BorerLootPolicy() {
	}
	/** Progress toward a route waypoint or actual block clearance counts, not just straight-line distance. */
	static final class Progress {
		private int idle;
		private double best = Double.POSITIVE_INFINITY;
		boolean tick(double distance, boolean picked, boolean cleared, boolean waypoint) {
			if (picked || cleared || waypoint || distance < best - .05) { best = distance; idle = 0; }
			else idle++;
			return idle >= 160;
		}
		int idleTicks() { return idle; }
	}
	static boolean keepItemTarget(double currentDistance, double nearestDistance) { return currentDistance <= nearestDistance + 1.5; }
	static boolean waitInsidePickupBox(int ticksWithoutPickup) { return ticksWithoutPickup < 20; }
	static boolean canStackDrop(boolean sameComponents, int count, int maximum) { return sameComponents && count < maximum; }
	static int verticalSearchRadius(boolean noFall) { return Math.max(10, BorerFallPolicy.maxSafeFallBlocks(noFall) + 2); }
	static boolean safeHop(boolean hop, boolean ceilingBlocked) { return hop && !ceilingBlocked; }
	static boolean trackDrop(boolean coalXp, boolean quartzXp, boolean coalDrop, boolean quartzDrop) {
		return !(coalXp && coalDrop || quartzXp && quartzDrop);
	}

	/**
	 * 已经捡过则只再等时运晚到的几拍；还没捡过才用刚挖掉的生成窗口。
	 */
	public static boolean spawnWaitElapsed(boolean alreadyPicked, int ticksSinceLastPickup) {
		int need = alreadyPicked ? EXTRA_SPAWN_TICKS : FIRST_SPAWN_TICKS;
		return ticksSinceLastPickup >= need;
	}

	/**
	 * 背包数量增加时要不要结束本轮。地上还有可追踪的同类、或时运掉落还可能在刷，
	 * 都不要收工。
	 */
	public static boolean finishOnInventoryIncrease(boolean matchingItemsRemain, boolean spawnWaitElapsed) {
		return !matchingItemsRemain && spawnWaitElapsed;
	}

	/**
	 * 视野里暂时没有掉落物：生成窗口没过完就继续等；已经见过则再确认几拍再走。
	 */
	public static boolean finishWhenMissing(boolean seenLoot, int missingTicks, boolean spawnWaitElapsed) {
		if (!spawnWaitElapsed) return false;
		return !seenLoot || missingTicks >= 4;
	}

	/** 地上没有、背包已经多了：不要再报「等待更多」。 */
	public static boolean overlayWaitForMore(boolean seenLoot, boolean itemsRemain, boolean alreadyPicked) {
		return seenLoot && !itemsRemain && !alreadyPicked;
	}

	/** 地上已经能看见同类掉落物时，先捡再挖旁边的矿。 */
	public static boolean collectVisibleBeforeAdjacent(boolean matchingItemsVisible) {
		return matchingItemsVisible;
	}

	/** 背包多了说明有进展；地上还有时清 stuck，不要当已经捡完。 */
	public static boolean inventoryProgressResetsStuck(boolean inventoryGrew, boolean matchingItemsRemain) {
		return inventoryGrew && matchingItemsRemain;
	}

	/**
	 * 原版 {@code ItemEntity} 拾取：玩家碰撞箱 {@code inflate(1.0, 0.5, 1.0)}，
	 * 半宽 0.3 后再扩 1，水平约 1.3 格；垂直从脚底 -0.5 到头顶 +0.5。
	 * dy=-1 的坑底站着捡不到。
	 */
	public static boolean inVanillaPickupRange(double dx, double dy, double dz) {
		return Math.abs(dx) <= 1.3 && Math.abs(dz) <= 1.3 && dy >= -0.5 && dy <= 2.3;
	}

	/** 掉落物在安全坑里：走进去，不要站在坑沿放弃。 */
	public static boolean shouldWalkIntoLootDrop(double dy, boolean dropSafe) {
		return dy < -0.25 && dropSafe;
	}

	/**
	 * 贴着安全坑沿却捡不到：跳一下才能迈出格子（1×2 里按 W 经常被卡在沿上）。
	 * 还没走到沿上、或已经在拾取箱里，不要跳。
	 */
	public static boolean shouldHopOffRim(boolean onGround, boolean safeLootDrop, double horiz, boolean inPickupRange) {
		return onGround && safeLootDrop && !inPickupRange && horiz <= 1.25;
	}

	/** 坑是 1×1、脚前空、头前能挖：挖头开 1×2 再下去。 */
	public static boolean shouldMineHeadToEnterLootDrop(double dy, boolean feetPassable, boolean headMineable) {
		return dy < -0.25 && BorerStairPolicy.mineHeadToOpenOneByTwo(feetPassable, headMineable);
	}

	/**
	 * 安全落差优先走下去，不要改去挖旁边挡路。
	 * 掉落物和人差不多高、中间隔着墙，不是落差，不要走这条。
	 */
	public static boolean preferDropOverMining(boolean safeLootDrop, boolean inPickupRange, double dy) {
		return safeLootDrop && !inPickupRange && dy < -0.25;
	}
}
