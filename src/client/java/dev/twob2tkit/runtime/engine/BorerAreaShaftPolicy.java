package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;

/**
 * 区域 1x1 竖井的确定性流程。挖、下潜、返顶和横移必须互斥，不能在井底斜飞到下一列。
 */
final class BorerAreaShaftPolicy {
	static final double CENTER_EPSILON = 0.08;
	/** 容纳 Meteor 单拍约 1 格的竖直步长；目标本身抬高 2 格，窗口下沿仍不会擦顶层方块。 */
	static final double HEIGHT_EPSILON = 0.55;

	/** 竖井流程阶段：就位 → 往下挖 → 返顶 → 换井平移。 */
	public enum Phase {
		POSITION_TOP,
		DIG_DOWN,
		ASCEND_CURRENT,
		TRANSFER_TOP
	}

	private BorerAreaShaftPolicy() {
	}

	/** 换井飞行目标脚底 Y。 */
	static int transferFeetY(int topY) {
		return topY + 2;
	}

	/** 顶到底都已清空，而且人物真的到达目标 Y，当前列才算完成。 */
	static boolean shaftComplete(boolean bounded, int feetY, int bottomY, boolean hasBlocks) {
		// 无目标 Y 时 bottomY 是世界底 -64；人物会站在基岩上方 -63，无法把脚放进 -64。
		int reachedY = bounded ? bottomY : bottomY + 1;
		return !hasBlocks && feetY <= reachedY;
	}

	/** 当前列脚下是空气时继续下降；即使中间是天然洞穴，也必须下到目标 Y。 */
	static boolean shouldDescend(boolean sameColumn, int feetY, int bottomY, boolean openBelow) {
		return sameColumn && feetY > bottomY && openBelow;
	}

	/** 是否已对准井心。 */
	static boolean centered(double playerX, double playerZ, int columnX, int columnZ) {
		return Math.max(
			Math.abs(columnX + 0.5 - playerX),
			Math.abs(columnZ + 0.5 - playerZ)) <= CENTER_EPSILON;
	}

	/** 是否低于换井高度。 */
	static boolean belowTransferHeight(double playerY, int topY) {
		return playerY < transferFeetY(topY) - HEIGHT_EPSILON;
	}

	/** 是否高于换井高度。 */
	static boolean aboveTransferHeight(double playerY, int topY) {
		return playerY > transferFeetY(topY) + HEIGHT_EPSILON;
	}

	/** 是否在换井高度带内。 */
	static boolean atTransferHeight(double playerY, int topY) {
		return !belowTransferHeight(playerY, topY) && !aboveTransferHeight(playerY, topY);
	}

	/** 正常返顶/换列不能让“想想”插入斜飞或跳井。 */
	static boolean allowThink(Phase phase, boolean genuinelyOccluded) {
		return phase == Phase.DIG_DOWN && genuinelyOccluded;
	}

	/** 本阶段遇障是否允许跳井。 */
	static boolean allowSkip(Phase phase, BlockPos obstacle, BlockPos current) {
		return phase == Phase.DIG_DOWN && sameColumn(obstacle, current);
	}

	/** 本阶段附近液体是否自行处理（否则交引擎）。 */
	static boolean handleNearbyLiquid(Phase phase, BlockPos liquid, BlockPos current) {
		return phase == Phase.DIG_DOWN;
	}

	/**
	 * 蛇形网格的下一列。相邻两项曼哈顿距离始终为 1；到末尾返回 null。
	 */
	static BlockPos nextSnakeColumn(int x, int z, int minX, int minZ, int maxX, int maxZ) {
		return nextSnakeColumn(x, z, minX, minZ, maxX, maxZ, minX, minZ);
	}

	/** 区域最近角点。 */
	static BlockPos nearestCorner(int px, int pz, int minX, int minZ, int maxX, int maxZ) {
		int x = Math.abs(px - minX) <= Math.abs(px - maxX) ? minX : maxX;
		int z = Math.abs(pz - minZ) <= Math.abs(pz - maxZ) ? minZ : maxZ;
		return new BlockPos(x, 0, z);
	}

	/** 从任意一个矩形角开始的连续蛇形；全程下一列都与上一列相邻。 */
	static BlockPos nextSnakeColumn(
		int x, int z, int minX, int minZ, int maxX, int maxZ, int startX, int startZ
	) {
		if (x < minX || x > maxX || z < minZ || z > maxZ) return null;
		if ((startX != minX && startX != maxX) || (startZ != minZ && startZ != maxZ)) return null;
		int stepX = startX == minX ? 1 : -1;
		int stepZ = startZ == minZ ? 1 : -1;
		int row = Math.abs(z - startZ);
		int rowStepX = (row & 1) == 0 ? stepX : -stepX;
		int rowEndX = rowStepX > 0 ? maxX : minX;
		if (x != rowEndX) return new BlockPos(x + rowStepX, 0, z);
		int endZ = stepZ > 0 ? maxZ : minZ;
		if (z != endZ) return new BlockPos(x, 0, z + stepZ);
		return null;
	}

	/** 两格是否同 XZ 柱。 */
	static boolean sameColumn(BlockPos a, BlockPos b) {
		return a != null && b != null && a.getX() == b.getX() && a.getZ() == b.getZ();
	}

	/**
	 * 不同阶段只允许挖对应列和高度，尤其禁止返顶时挖下一列的井底。
	 */
	static boolean allowsMine(
		Phase phase, BlockPos pos, BlockPos current, BlockPos pending, int topY, int bottomY
	) {
		if (phase == null || pos == null || current == null) return false;
		return switch (phase) {
			case DIG_DOWN -> sameColumn(pos, current) && pos.getY() >= bottomY && pos.getY() <= topY;
			case ASCEND_CURRENT -> sameColumn(pos, current) && pos.getY() >= bottomY;
			case POSITION_TOP -> sameColumn(pos, current) && pos.getY() >= bottomY;
			case TRANSFER_TOP -> pending != null
				&& sameColumn(pos, pending)
				&& pos.getY() >= transferFeetY(topY);
		};
	}
}
